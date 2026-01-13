import time
import threading
import tkinter as tk
import keyboard
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter
import json
import os

# ======================
# 配置
# ======================
CONFIG_FILE = "hud_config.json"
HOTKEY_TOGGLE = "F12"
HOTKEY_RESET = "F11"       # 只重置秒表时间
HOTKEY_RECORD = "F10"      # 记录当前时间
HOTKEY_RESET_ALL = "F9"    # 重置秒表 + 记录
HOTKEY_TOGGLE_HUD = "F8"   # 显示/隐藏 HUD
HOTKEY_ZOOM_OUT = "-"      # 缩小界面
HOTKEY_ZOOM_IN = "plus"    # 放大界面（+键）

# 默认字体大小
DEFAULT_FONT_SIZE = 48
DEFAULT_RECORD_FONT_SIZE = 24

# ======================
# 状态
# ======================
running = False
start_time = 0.0
elapsed = 0.0
laps = []
records = []  # 记录的时间列表
hud_visible = True   # 启动时默认显示
zoom_scale = 1.0     # 缩放比例，默认1.0，范围0.5-2.0

# ======================
# 配置读写
# ======================


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 兼容旧配置
            if "show_milliseconds" not in cfg:
                cfg["show_milliseconds"] = False
            if "zoom_scale" not in cfg:
                cfg["zoom_scale"] = 1.0
            return cfg
    return {"x": 600, "y": 300, "show_milliseconds": False, "zoom_scale": 1.0}


def save_config(x=None, y=None, show_milliseconds=None, zoom_scale=None):
    global config
    if x is not None and y is not None:
        config["x"] = x
        config["y"] = y
    if show_milliseconds is not None:
        config["show_milliseconds"] = show_milliseconds
    if zoom_scale is not None:
        config["zoom_scale"] = zoom_scale
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f)


config = load_config()
zoom_scale = config.get("zoom_scale", 1.0)  # 从配置加载缩放比例

# ======================
# 秒表逻辑
# ======================


def toggle_timer():
    global running, start_time, elapsed
    if not running:
        start_time = time.time() - elapsed
        running = True
    else:
        elapsed = time.time() - start_time
        running = False


def record_lap():
    if running:
        laps.append(elapsed)
        print(f"[LAP {len(laps)}] {format_time(elapsed)}")


def record_time():
    """记录当前时间"""
    global records
    records.append(elapsed)
    # 使用 root.after 确保在主线程中更新 UI
    root.after(0, update_records_display)


def reset_timer():
    """只重置秒表时间，不清除记录"""
    global running, elapsed, start_time, laps
    running = False
    elapsed = 0.0
    laps.clear()
    start_time = time.time()
    # 使用 root.after 确保在主线程中更新 UI
    root.after(0, update_label)

def zoom_in():
    """放大界面"""
    global zoom_scale
    zoom_scale = min(zoom_scale + 0.1, 2.0)  # 最大2倍
    save_config(zoom_scale=zoom_scale)
    root.after(0, update_label)
    root.after(0, update_records_display)

def zoom_out():
    """缩小界面"""
    global zoom_scale
    zoom_scale = max(zoom_scale - 0.1, 0.25)  # 最小0.25倍
    save_config(zoom_scale=zoom_scale)
    root.after(0, update_label)
    root.after(0, update_records_display)


def reset_all():
    """重置秒表时间 + 记录"""
    global running, elapsed, start_time, laps, records
    running = False
    elapsed = 0.0
    laps.clear()
    records.clear()
    start_time = time.time()
    # 使用 root.after 确保在主线程中更新 UI
    root.after(0, update_label)
    root.after(0, update_records_display)

# ======================
# HUD 显示
# ======================


def format_time(sec):
    s = int(sec) % 60
    m = int(sec) // 60
    if config.get("show_milliseconds", False):
        ms = int((sec - int(sec)) * 1000)
        return f"{m:02d}:{s:02d}.{ms:03d}"
    else:
        return f"{m:02d}:{s:02d}"


def draw_rounded_rectangle_smooth(xy, fill, radius=10):
    """绘制平滑的圆角矩形（使用像素级透明度渐变实现抗锯齿）"""
    import math
    x1, y1, x2, y2 = xy
    width = x2 - x1 + 1
    height = y2 - y1 + 1
    
    # 使用更高的超采样：6倍超采样以获得更平滑的效果
    scale = 6
    large_width = width * scale
    large_height = height * scale
    large_radius = radius * scale
    
    # 创建高分辨率临时图像
    temp_img = Image.new("RGBA", (large_width, large_height), (0, 0, 0, 0))
    pixels = temp_img.load()
    
    # 获取填充颜色
    r, g, b = fill[:3]
    alpha = fill[3] if len(fill) > 3 else 255
    
    # 圆角中心坐标
    corners = [
        (large_radius, large_radius),  # 左上
        (large_width - large_radius, large_radius),  # 右上
        (large_radius, large_height - large_radius),  # 左下
        (large_width - large_radius, large_height - large_radius)  # 右下
    ]
    
    # 边缘过渡宽度（在超采样空间中，更宽的过渡区域）
    edge_width = 2.0 * scale  # 增加到2像素的过渡宽度
    
    # 逐像素绘制，计算每个像素到圆角边界的距离
    for y in range(large_height):
        for x in range(large_width):
            # 检查是否在矩形主体内（不在圆角区域）
            in_rect = (x >= large_radius and x < large_width - large_radius) or \
                     (y >= large_radius and y < large_height - large_radius)
            
            if in_rect:
                # 在矩形主体内，完全不透明
                pixels[x, y] = (r, g, b, alpha)
            else:
                # 在圆角区域，计算到最近圆角中心的距离
                min_dist = float('inf')
                for cx, cy in corners:
                    # 计算到圆角中心的距离
                    dx = x - cx
                    dy = y - cy
                    dist = math.sqrt(dx*dx + dy*dy)
                    
                    # 计算到圆角边界的距离
                    dist_to_edge = dist - large_radius
                    min_dist = min(min_dist, dist_to_edge)
                
                # 根据距离设置透明度（实现平滑过渡）
                if min_dist <= 0:
                    # 在圆角内部，完全不透明
                    pixel_alpha = alpha
                elif min_dist < edge_width:
                    # 在边缘过渡区域，计算渐变透明度
                    # 使用更平滑的过渡函数（改进的smoothstep）
                    t = min_dist / edge_width
                    # 使用更平滑的曲线：smoothstep的改进版本
                    t = t * t * t * (t * (t * 6 - 15) + 10)  # smootherstep函数，更平滑
                    pixel_alpha = int(alpha * (1 - t))
                else:
                    # 在圆角外部，完全透明
                    pixel_alpha = 0
                
                pixels[x, y] = (r, g, b, pixel_alpha)
    
    # 缩放回原始尺寸（使用最高质量的LANCZOS重采样）
    final_img = temp_img.resize((width, height), Image.Resampling.LANCZOS)
    
    return final_img

def create_text_image(text, font_size=48, align="left", target_width=None, target_height=None):
    """使用 PIL 创建文字图像，获得更好的抗锯齿效果
    align: "left", "center", "right" - 文本对齐方式
    target_width: 如果指定，图像将使用此宽度（用于居中对齐）
    target_height: 如果指定，图像将使用此高度（用于固定高度）
    """
    # 创建临时图像来测量文字大小
    temp_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)

    # 尝试加载 Consolas 字体（Windows 系统字体）
    font = None
    font_paths = [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/consolab.ttf",
        "consola.ttf",
        "consolab.ttf",
    ]

    for path in font_paths:
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except:
            continue

    # 如果都失败了，尝试使用系统默认等宽字体
    if font is None:
        try:
            # Windows 上尝试使用 Courier New
            font = ImageFont.truetype("C:/Windows/Fonts/cour.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype(
                    "C:/Windows/Fonts/courbd.ttf", font_size)
            except:
                font = ImageFont.load_default()

    # 获取文字边界框（处理多行文本）
    lines = text.split('\n')
    if len(lines) > 1:
        # 多行文本：计算每行的宽度和总高度
        line_heights = []
        max_width = 0
        for line in lines:
            bbox = temp_draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            line_heights.append(line_height)
            max_width = max(max_width, line_width)
        text_width = max_width
        text_height = sum(line_heights) + (len(lines) - 1) * 5  # 行间距5像素
    else:
        # 单行文本
        bbox = temp_draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

    # 创建实际图像，添加一些边距（左侧10像素，右侧10像素）
    padding = 15
    # 如果指定了目标宽度，使用目标宽度；否则根据文本宽度计算
    if target_width is not None:
        img_width = target_width
    else:
        img_width = text_width + padding * 2
    # 如果指定了目标高度，使用目标高度；否则根据文本高度计算
    if target_height is not None:
        img_height = target_height
    else:
        img_height = text_height + padding * 2
    radius = 8
    bg_color = (26, 26, 26, 255)
    
    # 使用超采样绘制平滑的圆角矩形背景
    bg_img = draw_rounded_rectangle_smooth((0, 0, img_width - 1, img_height - 1), fill=bg_color, radius=radius)
    
    # 创建主图像并粘贴背景
    img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    img.paste(bg_img, (0, 0), bg_img)  # 使用alpha通道合成
    draw = ImageDraw.Draw(img)

    # 绘制文字，根据对齐方式设置位置
    text_y = padding
    if len(lines) > 1:
        # 多行文本：逐行绘制
        y_offset = text_y
        for line in lines:
            if line.strip():  # 跳过空行
                # 计算文本宽度以确定x位置
                line_bbox = temp_draw.textbbox((0, 0), line, font=font)
                line_width = line_bbox[2] - line_bbox[0]
                
                if align == "center":
                    text_x = (img_width - line_width) // 2
                    anchor = "lt"
                elif align == "right":
                    text_x = img_width - padding - line_width
                    anchor = "lt"
                else:  # left
                    text_x = padding
                    anchor = "lt"
                
                draw.text((text_x, y_offset), line, fill=(0, 255, 170, 255), font=font, anchor=anchor)
                # 计算下一行的位置
                bbox = temp_draw.textbbox((0, 0), line, font=font)
                y_offset += (bbox[3] - bbox[1]) + 5  # 行高 + 间距
    else:
        # 单行文本
        if align == "center":
            text_x = (img_width - text_width) // 2
            anchor = "lt"
        elif align == "right":
            text_x = img_width - padding - text_width
            anchor = "lt"
        else:  # left
            text_x = padding
            anchor = "lt"
        draw.text((text_x, text_y), text, fill=(0, 255, 170, 255), font=font, anchor=anchor)

    return img


def update_label():
    text = format_time(elapsed)
    font_size = int(DEFAULT_FONT_SIZE * zoom_scale)
    
    # 计算最大可能的时间（99:59 或 99:59.999），用于固定背景宽度和高度
    max_time_text = "99:59.999" if config.get("show_milliseconds", False) else "99:59"
    max_img = create_text_image(max_time_text, font_size=font_size)
    fixed_width = max_img.width
    fixed_height = max_img.height
    
    # 使用固定宽度和高度创建图像，避免背景大小变化
    img = create_text_image(text, font_size=font_size, target_width=fixed_width, target_height=fixed_height, align="center")
    photo = ImageTk.PhotoImage(img)
    label.config(image=photo)
    label.image = photo  # 保持引用


def update_records_display():
    """更新记录显示"""
    if not records:
        # 创建一个空的透明图像
        empty_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        empty_photo = ImageTk.PhotoImage(empty_img)
        records_label.config(image=empty_photo)
        records_label.image = empty_photo
        return

    # 只显示最近5条记录，去掉序号，只显示时间
    recent_records = records[-5:]
    records_text = "\n".join([format_time(t) for t in recent_records])

    record_font_size = int(DEFAULT_RECORD_FONT_SIZE * zoom_scale)
    
    # 获取秒表时间的宽度，让记录时间使用相同的宽度以实现居中对齐
    main_font_size = int(DEFAULT_FONT_SIZE * zoom_scale)
    main_text = format_time(elapsed)
    main_img = create_text_image(main_text, font_size=main_font_size)
    target_width = main_img.width
    
    # 使用居中对齐，并指定目标宽度
    img = create_text_image(records_text, font_size=record_font_size, align="center", target_width=target_width)
    photo = ImageTk.PhotoImage(img)
    records_label.config(image=photo)
    records_label.image = photo  # 保持引用


def update_loop():
    global elapsed
    if running:
        elapsed = time.time() - start_time
        update_label()
    root.after(30, update_loop)

# ======================
# HUD 显隐
# ======================


def toggle_hud():
    global hud_visible
    hud_visible = not hud_visible
    if hud_visible:
        root.deiconify()
    else:
        root.withdraw()

# ======================
# HUD 拖拽和右键菜单
# ======================

def show_context_menu(event):
    """显示右键菜单"""
    context_menu = tk.Menu(root, tearoff=0, bg="#2a2a2a", fg="#ffffff", 
                          activebackground="#00FFAA", activeforeground="#000000")
    
    format_text = "显示毫秒" if not config.get("show_milliseconds", False) else "隐藏毫秒"
    
    context_menu.add_command(label="显示 / 隐藏 HUD", command=toggle_hud)
    context_menu.add_separator()
    context_menu.add_command(label=format_text, command=toggle_time_format)
    context_menu.add_separator()
    context_menu.add_command(label="重置计时", command=reset_timer)
    context_menu.add_command(label="重置全部（含记录）", command=reset_all)
    context_menu.add_separator()
    context_menu.add_command(label="退出", command=on_exit)
    
    try:
        context_menu.tk_popup(event.x_root, event.y_root)
    finally:
        context_menu.grab_release()

def start_drag(event):
    root._drag_x = event.x
    root._drag_y = event.y


def on_drag(event):
    x = root.winfo_x() + event.x - root._drag_x
    y = root.winfo_y() + event.y - root._drag_y
    root.geometry(f"+{x}+{y}")


def stop_drag(event):
    save_config(x=root.winfo_x(), y=root.winfo_y())

# ======================
# 键盘监听
# ======================


def keyboard_listener():
    keyboard.add_hotkey(HOTKEY_TOGGLE, toggle_timer)
    keyboard.add_hotkey(HOTKEY_RESET, reset_timer)
    keyboard.add_hotkey(HOTKEY_RECORD, record_time)
    keyboard.add_hotkey(HOTKEY_RESET_ALL, reset_all)
    keyboard.add_hotkey(HOTKEY_TOGGLE_HUD, toggle_hud)
    keyboard.add_hotkey(HOTKEY_ZOOM_IN, zoom_in)
    keyboard.add_hotkey(HOTKEY_ZOOM_OUT, zoom_out)
    keyboard.wait()

# ======================
# 托盘
# ======================


def toggle_time_format():
    global config
    config["show_milliseconds"] = not config.get("show_milliseconds", False)
    save_config(show_milliseconds=config["show_milliseconds"])
    update_label()
    # 更新托盘菜单
    update_tray_menu()


def update_tray_menu():
    global tray_icon
    if tray_icon is None:
        return
    image = Image.new("RGB", (64, 64), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 18, 46, 46), outline="#00FFAA", width=4)

    format_text = "显示毫秒" if not config.get(
        "show_milliseconds", False) else "隐藏毫秒"

    menu = (
        item("显示 / 隐藏 HUD", toggle_hud),
        item(format_text, toggle_time_format),
        item("重置计时（含记录）", reset_all),
        item("退出", on_exit),
    )

    tray_icon.menu = pystray.Menu(*menu)
    tray_icon.update_menu()


def create_tray_icon():
    global tray_icon
    image = Image.new("RGB", (64, 64), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 18, 46, 46), outline="#00FFAA", width=4)

    format_text = "显示毫秒" if not config.get(
        "show_milliseconds", False) else "隐藏毫秒"

    menu = (
        item("显示 / 隐藏 HUD", toggle_hud),
        item(format_text, toggle_time_format),
        item("重置计时（含记录）", reset_all),
        item("退出", on_exit),
    )

    tray_icon = pystray.Icon("F12Stopwatch", image, "F12 Stopwatch", menu)
    tray_icon.run()


def on_exit():
    tray_icon.stop()
    root.quit()


# ======================
# Tk HUD
# ======================
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-transparentcolor", "black")
root.configure(bg="black", highlightthickness=0, bd=0)

root.geometry(f"+{config['x']}+{config['y']}")

# 创建主容器 Frame
main_frame = tk.Frame(root, bg="black", highlightthickness=0, bd=0)
main_frame.pack(fill=tk.BOTH, expand=True, anchor="w")  # 左对齐

# 创建初始图像（使用缩放后的字体大小）
initial_font_size = int(DEFAULT_FONT_SIZE * zoom_scale)
# 计算最大可能的时间，用于固定背景宽度和高度
max_time_text = "99:59.999" if config.get("show_milliseconds", False) else "99:59"
max_img = create_text_image(max_time_text, font_size=initial_font_size)
fixed_width = max_img.width
fixed_height = max_img.height
initial_img = create_text_image(format_time(0), font_size=initial_font_size, target_width=fixed_width, target_height=fixed_height, align="center")
initial_photo = ImageTk.PhotoImage(initial_img)

label = tk.Label(
    main_frame,
    image=initial_photo,
    bg="black",
    bd=0,
    padx=0,
    pady=0,
    highlightthickness=0,
    anchor="w"  # 左对齐
)
label.image = initial_photo  # 保持引用
label.pack(padx=0, pady=(0, 8), anchor="w")  # 左对齐，底部间距8像素

# 创建记录显示标签
records_label = tk.Label(
    main_frame,
    bg="black",
    bd=0,
    padx=0,
    pady=0,
    highlightthickness=0,
    anchor="w"  # 左对齐
)
records_label.pack(padx=0, pady=0, anchor="w")  # 左对齐

# 绑定拖拽事件到主容器
main_frame.bind("<Button-1>", start_drag)
main_frame.bind("<B1-Motion>", on_drag)
main_frame.bind("<ButtonRelease-1>", stop_drag)
main_frame.bind("<Button-3>", show_context_menu)  # 右键菜单
label.bind("<Button-1>", start_drag)
label.bind("<B1-Motion>", on_drag)
label.bind("<ButtonRelease-1>", stop_drag)
label.bind("<Button-3>", show_context_menu)  # 右键菜单
records_label.bind("<Button-1>", start_drag)
records_label.bind("<B1-Motion>", on_drag)
records_label.bind("<ButtonRelease-1>", stop_drag)
records_label.bind("<Button-3>", show_context_menu)  # 右键菜单

# 启动时显示
root.deiconify()

# ======================
# 启动线程
# ======================
tray_icon = None
threading.Thread(target=create_tray_icon, daemon=True).start()
threading.Thread(target=keyboard_listener, daemon=True).start()

update_loop()
root.mainloop()
