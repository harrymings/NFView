"""Metadata functionality for NFView."""
from __future__ import annotations
import struct
import exifread


from nfview.resources import RAW_EXTENSIONS

def recorded_focus_boxes(path, preview_size):
    """Decode Nikon's recorded AF areas; never infer focus from image content.

    AFInfo2 offsets follow ExifTool's Nikon table:
    https://exiftool.org/TagNames/Nikon.html#AFInfo2V0400
    Coordinates are normalized to the displayed preview, including orientation.
    Unsupported/missing records return an explicit explanation, never a guess.
    """
    try:
        with path.open("rb") as stream:
            endian = stream.read(2)
            stream.seek(0)
            tags = exifread.process_file(stream, details=True)
        model = str(tags.get("Image Model", ""))
        tag = tags.get("MakerNote AFInfo2")
        if not model.upper().startswith("NIKON") or tag is None:
            return [], "No recorded Nikon autofocus coordinates in this file."
        data = bytes(tag.values)
        version = data[:4]
        if version in (b"0400", b"0401", b"0402") and len(data)>=75:
            origin, flag = 62, data[7]
        elif version in (b"0300", b"0301") and len(data)>=54:
            origin, flag = 42, data[7]
        else:
            return [], "This camera's autofocus metadata layout is not supported."
        maker=tags.get("EXIF MakerNote")
        if maker and bytes(maker.values[:6]) == b"Nikon\x00":
            maker_order=bytes(maker.values[10:12])
            if maker_order in (b"II",b"MM"):
                endian=maker_order
        order = ">" if endian == b"MM" else "<"
        width,height,x,y,bw,bh = struct.unpack_from(order+"6H", data, origin)
        if not width or not height:
            return [], "The camera did not save an autofocus coordinate frame."
        boxes = []
        if flag == 1 and 0<x<width and 0<y<height and bw and bh:
            boxes.append(((x-bw/2)/width,(y-bh/2)/height,(x+bw/2)/width,(y+bh/2)/height))
            note = "Recorded Nikon AF area. It marks the camera's AF area, not a guarantee of sharpness."
        elif flag == 0 and version.startswith(b"04") and data[5] in (197,207):
            # Expeed 7 auto-area bitmaps are row-major, least-significant bit first.
            # The documented grid spacing is 260 AF pixels horizontally. Full-frame
            # 24MP cameras use 299 points; 45MP cameras use 405. Unsupported grids
            # are deliberately omitted rather than drawing invented points.
            if model in ("NIKON Z5_2", "NIKON Z6_3", "NIKON Z f"):
                cols,rows,step_x,step_y = 23,13,260,286
            elif model in ("NIKON Z 8", "NIKON Z 9"):
                cols,rows,step_x,step_y = 27,15,260,292
            elif model == "NIKON Z50_2":
                cols,rows,step_x,step_y = 21,11,260,286
            else:
                return [], "Autofocus point grid is not supported for this camera."
            for index in range(cols*rows):
                if data[10+index//8] & (1<<(index%8)):
                    cx = width/2+(index%cols-(cols-1)/2)*step_x
                    cy = height/2+(index//cols-(rows-1)/2)*step_y
                    boxes.append(((cx-step_x/2)/width,(cy-step_y/2)/height,(cx+step_x/2)/width,(cy+step_y/2)/height))
            note = "Recorded Nikon AF points; grid-cell positions are approximate."
        else:
            return [], "No autofocus area was recorded for this exposure."
        if not boxes:
            return [], "The camera recorded no active autofocus points."
        orientation_tag=tags.get("Image Orientation")
        orientation=int(orientation_tag.values[0]) if orientation_tag else 1
        # Some RAW previews omit rotation. Match the image actually displayed.
        if path.suffix.lower() in RAW_EXTENSIONS and orientation in (5,6,7,8):
            if (preview_size[0]>preview_size[1]) == (width>height):
                orientation=1
        def orient(u,v):
            return {1:(u,v),2:(1-u,v),3:(1-u,1-v),4:(u,1-v),
                    5:(v,u),6:(1-v,u),7:(1-v,1-u),8:(v,1-u)}.get(orientation,(u,v))
        oriented=[]
        for left,top,right,bottom in boxes:
            corners=[orient(u,v) for u,v in ((left,top),(right,top),(left,bottom),(right,bottom))]
            oriented.append((max(0,min(c[0] for c in corners)),max(0,min(c[1] for c in corners)),
                             min(1,max(c[0] for c in corners)),min(1,max(c[1] for c in corners))))
        return oriented,note
    except (OSError,ValueError,TypeError,IndexError,struct.error):
        return [], "Autofocus metadata could not be read."
