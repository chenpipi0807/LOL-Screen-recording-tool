from PIL import Image, ImageDraw

sizes = [256, 128, 64, 48, 32, 16]
imgs = []

for s in sizes:
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    margin = int(s * 0.0625)
    r = int(s * 0.125)
    
    # 背景圆角矩形 - 渐变蓝紫色
    draw.rounded_rectangle([margin, margin, s-margin, s-margin], radius=r, fill=(137, 180, 250))
    
    cx, cy = s//2, s//2
    
    # 外圈深色
    cr = int(s * 0.273)
    draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=(30, 30, 46))
    
    # 内圈红色录制按钮
    cr2 = int(s * 0.195)
    draw.ellipse([cx-cr2, cy-cr2, cx+cr2, cy+cr2], fill=(255, 85, 85))
    
    imgs.append(img)

imgs[0].save('icon.ico', format='ICO', sizes=[(s, s) for s in sizes], append_images=imgs[1:])
print("icon.ico created successfully!")
