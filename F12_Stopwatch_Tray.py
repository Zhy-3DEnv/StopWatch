import time
import threading
import tkinter as tk
from tkinter import simpledialog
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
HOTKEY_TOGGLE = "F12"        # 切换秒表开始/停止
HOTKEY_RESET = "F11"         # 单击：重置秒表；双击：重置秒表和记录
HOTKEY_RECORD = "F10"        # 单击：记录时间；双击：显示/隐藏HUD
HOTKEY_EDIT_NOTE = "F7"      # 为最近一次记录添加/编辑说明
HOTKEY_ZOOM_OUT = "-"        # 缩小界面
HOTKEY_ZOOM_IN = "plus"      # 放大界面（+键）

# 默认字体大小（已调整为原来的50%）
DEFAULT_FONT_SIZE = 24  # 原来48，现在24（50%）
DEFAULT_RECORD_FONT_SIZE = 18  # 原来36，现在18（50%）

# ======================
# 状态
# ======================
running = False
start_time = 0.0
elapsed = 0.0
laps = []
# 记录结构：{"time": float, "note": str}
records = []  # 记录的时间列表
hud_visible = True   # 启动时默认显示
zoom_scale = 1.0     # 缩放比例，默认1.0，范围0.5-2.0

# 主秒表显示缓存，减少重复计算和重绘
fixed_width = None
fixed_height = None
last_display_text = None

# 圆角背景缓存：key = (width, height, radius, fill)
bg_cache = {}

# 是否正在拖拽 HUD，用于在拖拽时减轻重绘负担
is_dragging = False

# 当前记录区域中“可见的记录”在 records 列表中的下标，供右键精确定位
visible_record_indices = []

# 双击检测：记录按键时间和延迟执行的Timer
key_timers = {}  # key -> threading.Timer对象
key_last_press = {}  # key -> 最后按下时间
DOUBLE_CLICK_DELAY = 0.3  # 双击间隔300ms
SINGLE_CLICK_DELAY = 0.35  # 单击延迟执行时间350ms

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
    try:
        global running, start_time, elapsed, last_display_text
        if not running:
            start_time = time.time() - elapsed
            running = True
        else:
            elapsed = time.time() - start_time
            running = False
        # 状态切换时重置缓存，触发一次更新
        last_display_text = None
        root.after(0, update_label)
    except Exception as e:
        print(f"Error in toggle_timer: {e}")


def record_lap():
    if running:
        laps.append(elapsed)
        print(f"[LAP {len(laps)}] {format_time(elapsed)}")


def record_time():
    """记录当前时间（新增一条记录，可后续添加备注）"""
    try:
        global records
        records.append({"time": elapsed, "note": ""})
        # 使用 root.after 确保在主线程中更新 UI
        root.after(0, update_records_display)
    except Exception as e:
        print(f"Error in record_time: {e}")


def reset_timer():
    """只重置秒表时间，不清除记录"""
    try:
        global running, elapsed, start_time, laps
        running = False
        elapsed = 0.0
        laps.clear()
        start_time = time.time()
        # 使用 root.after 确保在主线程中更新 UI
        root.after(0, update_label)
    except Exception as e:
        print(f"Error in reset_timer: {e}")


def show_zoom_percentage():
    """显示缩放百分比（相对于默认大小），2秒后自动隐藏"""
    try:
        global zoom_label
        # 相对于默认大小（1.0）的百分比
        percentage = int(zoom_scale * 100)
        zoom_label.config(text=f"{percentage}%", fg="#00FFAA")
        zoom_label.pack(pady=(5, 0))
        
        # 2秒后隐藏
        root.after(2000, lambda: zoom_label.pack_forget())
    except Exception as e:
        print(f"Error in show_zoom_percentage: {e}")


def zoom_in():
    """放大界面（每次增加5%）"""
    try:
        global zoom_scale, fixed_width, fixed_height, last_display_text
        zoom_scale = min(zoom_scale + 0.05, 2.0)  # 每次增加5%，最大2倍（200%）
        save_config(zoom_scale=zoom_scale)
        # 缩放改变后需要重新计算固定尺寸并强制重绘
        fixed_width = None
        fixed_height = None
        last_display_text = None
        root.after(0, update_label)
        root.after(0, update_records_display)
        root.after(0, show_zoom_percentage)
    except Exception as e:
        print(f"Error in zoom_in: {e}")


def zoom_out():
    """缩小界面（每次减少5%）"""
    try:
        global zoom_scale, fixed_width, fixed_height, last_display_text
        zoom_scale = max(zoom_scale - 0.05, 0.25)  # 每次减少5%，最小0.25倍（25%）
        save_config(zoom_scale=zoom_scale)
        # 缩放改变后需要重新计算固定尺寸并强制重绘
        fixed_width = None
        fixed_height = None
        last_display_text = None
        root.after(0, update_label)
        root.after(0, update_records_display)
        root.after(0, show_zoom_percentage)
    except Exception as e:
        print(f"Error in zoom_out: {e}")


def recalc_main_fixed_size():
    """根据当前配置和缩放，重新计算主秒表固定宽高"""
    global fixed_width, fixed_height
    font_size = int(DEFAULT_FONT_SIZE * zoom_scale)
    max_time_text = "99:59.999" if config.get(
        "show_milliseconds", False) else "99:59"
    max_img = create_text_image(max_time_text, font_size=font_size)
    fixed_width = max_img.width
    fixed_height = max_img.height


def reset_all():
    """重置秒表时间 + 记录"""
    try:
        global running, elapsed, start_time, laps, records, last_display_text
        running = False
        elapsed = 0.0
        laps.clear()
        records.clear()
        last_display_text = None
        start_time = time.time()
        # 使用 root.after 确保在主线程中更新 UI
        root.after(0, update_label)
        root.after(0, update_records_display)
    except Exception as e:
        print(f"Error in reset_all: {e}")

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

    # 先检查缓存，避免重复计算
    key = (width, height, radius, tuple(fill))
    if key in bg_cache:
        return bg_cache[key]

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
                    # smootherstep函数，更平滑
                    t = t * t * t * (t * (t * 6 - 15) + 10)
                    pixel_alpha = int(alpha * (1 - t))
                else:
                    # 在圆角外部，完全透明
                    pixel_alpha = 0

                pixels[x, y] = (r, g, b, pixel_alpha)

    # 缩放回原始尺寸（使用最高质量的LANCZOS重采样）
    final_img = temp_img.resize((width, height), Image.Resampling.LANCZOS)

    # 写入缓存
    bg_cache[key] = final_img
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

    # 尝试加载支持中文的字体（优先微软雅黑等）
    font = None
    font_paths = [
        # 常见中文字体（简体中文 Windows 下一般存在）
        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",    # 微软雅黑加粗
        "C:/Windows/Fonts/simhei.ttf",    # 黑体
        "C:/Windows/Fonts/simsun.ttc",    # 宋体
        # 退回到原来的英文字体作为兜底
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

    # 使用背景：拖拽时用简单矩形以提升性能，非拖拽时用圆角抗锯齿
    if is_dragging:
        # 简单矩形背景（无圆角），性能更好
        bg_img = Image.new("RGBA", (img_width, img_height), bg_color)
    else:
        # 使用超采样绘制平滑的圆角矩形背景（带缓存）
        bg_img = draw_rounded_rectangle_smooth(
            (0, 0, img_width - 1, img_height - 1), fill=bg_color, radius=radius)

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

                draw.text((text_x, y_offset), line, fill=(
                    0, 255, 170, 255), font=font, anchor=anchor)
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
        draw.text((text_x, text_y), text, fill=(
            0, 255, 170, 255), font=font, anchor=anchor)

    return img


def update_label():
    """更新主秒表显示，带缓存以减少重绘"""
    global fixed_width, fixed_height, last_display_text
    text = format_time(elapsed)

    # 如果显示内容没变且已有固定尺寸，直接返回，避免重复重绘
    if text == last_display_text and fixed_width is not None and fixed_height is not None:
        return

    # 如有需要，重新计算固定宽高
    if fixed_width is None or fixed_height is None:
        recalc_main_fixed_size()

    font_size = int(DEFAULT_FONT_SIZE * zoom_scale)

    # 使用固定宽度和高度创建图像，避免背景大小变化
    img = create_text_image(
        text,
        font_size=font_size,
        target_width=fixed_width,
        target_height=fixed_height,
        align="center",
    )
    photo = ImageTk.PhotoImage(img)
    label.config(image=photo)
    label.image = photo  # 保持引用
    last_display_text = text


def update_records_display():
    """更新记录显示"""
    global visible_record_indices

    if not records:
        # 创建一个空的透明图像
        empty_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        empty_photo = ImageTk.PhotoImage(empty_img)
        records_label.config(image=empty_photo)
        records_label.image = empty_photo
        visible_record_indices = []
        return

    # 只显示最近5条记录，格式：时间 + 可选说明
    total = len(records)
    start_index = max(0, total - 5)
    visible_record_indices = list(range(start_index, total))
    recent_records = [records[i] for i in visible_record_indices]

    lines = []
    for rec in recent_records:
        # 向后兼容旧结构：可能是 float
        if isinstance(rec, dict):
            t = rec.get("time", 0.0)
            note = rec.get("note", "")
        else:
            t = float(rec)
            note = ""
        line = format_time(t)
        if note:
            line = f"{line}  {note}"
        lines.append(line)
    records_text = "\n".join(lines)

    record_font_size = int(DEFAULT_RECORD_FONT_SIZE * zoom_scale)

    # 记录区域的宽度：取“主秒表固定宽度”和“记录自然宽度”的较大值，
    # 这样既保证不截断长说明，又尽量与上方秒表对齐
    global fixed_width, fixed_height
    if fixed_width is None or fixed_height is None:
        recalc_main_fixed_size()

    # 先生成一张不限制宽度的临时图像，用于测量自然宽度
    temp_img = create_text_image(records_text, font_size=record_font_size, align="left")
    natural_width = temp_img.width
    target_width = max(fixed_width, natural_width)

    # 使用左对齐，并指定目标宽度（时间列从左侧整齐对齐）
    img = create_text_image(records_text, font_size=record_font_size,
                            align="left", target_width=target_width)
    photo = ImageTk.PhotoImage(img)
    records_label.config(image=photo)
    records_label.image = photo  # 保持引用


def update_loop():
    global elapsed
    if running:
        elapsed = time.time() - start_time
        # 拖拽时也保持更新显示（已通过缓存和优化降低重绘开销）
        update_label()
    # 拖拽时降低更新频率到10fps（100ms），非拖拽时使用更高频率（30ms约33fps）
    if is_dragging:
        root.after(100, update_loop)  # 拖拽时10fps
    else:
        root.after(30, update_loop)  # 非拖拽时约33fps

# ======================
# HUD 显隐
# ======================


def toggle_hud():
    try:
        global hud_visible
        hud_visible = not hud_visible
        if hud_visible:
            root.deiconify()
        else:
            root.withdraw()
    except Exception as e:
        print(f"Error in toggle_hud: {e}")

# ======================
# HUD 拖拽和右键菜单
# ======================


def reset_to_default_settings():
    """恢复默认设置"""
    try:
        global zoom_scale, fixed_width, fixed_height, last_display_text, config
        # 恢复缩放比例到 1.0（100%）
        zoom_scale = 1.0
        save_config(zoom_scale=zoom_scale)
        # 重置缓存，强制重绘
        fixed_width = None
        fixed_height = None
        last_display_text = None
        root.after(0, update_label)
        root.after(0, update_records_display)
        # 显示恢复提示
        root.after(0, show_zoom_percentage)
    except Exception as e:
        print(f"Error in reset_to_default_settings: {e}")


def show_context_menu(event):
    """显示右键菜单"""
    context_menu = tk.Menu(root, tearoff=0, bg="#2a2a2a", fg="#ffffff",
                           activebackground="#00FFAA", activeforeground="#000000")

    format_text = "显示毫秒" if not config.get(
        "show_milliseconds", False) else "隐藏毫秒"

    # 使用用户要求的格式：功能名称（快捷键）
    context_menu.add_command(label="显示 / 隐藏 HUD（双击F10）", command=toggle_hud)
    context_menu.add_separator()
    context_menu.add_command(label=format_text, command=toggle_time_format)
    context_menu.add_separator()
    context_menu.add_command(label="重置计时（单击F11）", command=reset_timer)
    context_menu.add_command(label="重置全部（含记录）（双击F11）", command=reset_all)
    context_menu.add_separator()
    context_menu.add_command(label="为最近一次记录添加说明（F7）", command=add_record_note)
    context_menu.add_separator()
    context_menu.add_command(label="恢复默认设置", command=reset_to_default_settings)
    context_menu.add_separator()
    context_menu.add_command(label="退出", command=on_exit)

    try:
        context_menu.tk_popup(event.x_root, event.y_root)
    finally:
        context_menu.grab_release()


def start_drag(event):
    global is_dragging
    is_dragging = True
    root._drag_x = event.x
    root._drag_y = event.y


def on_drag(event):
    x = root.winfo_x() + event.x - root._drag_x
    y = root.winfo_y() + event.y - root._drag_y
    root.geometry(f"+{x}+{y}")


def stop_drag(event):
    global is_dragging
    is_dragging = False
    save_config(x=root.winfo_x(), y=root.winfo_y())
    # 拖拽结束后补一次重绘，保证显示最新时间
    update_label()


def _edit_record_note_by_index(index: int):
    """按下标为指定记录添加/编辑文字说明"""
    try:
        global records
        if not records or index < 0 or index >= len(records):
            return

        rec = records[index]
        if isinstance(rec, dict):
            current_note = rec.get("note", "")
            t = rec.get("time", 0.0)
        else:
            # 兼容旧结构：只有时间
            current_note = ""
            t = float(rec)
            # 升级为新结构
            rec = {"time": t, "note": current_note}
            records[index] = rec

        # 弹出输入框，让用户填写说明
        prompt_title = "记录说明"
        prompt_text = f"为该记录添加说明（时间：{format_time(t)}）："
        note = simpledialog.askstring(prompt_title, prompt_text, initialvalue=current_note)
        if note is None:
            return  # 用户取消

        rec["note"] = note.strip()
        # 更新显示
        root.after(0, update_records_display)
    except Exception as e:
        print(f"Error in add_record_note: {e}")


def add_record_note():
    """为最近一次记录添加/编辑文字说明（F7 / 右键菜单使用）"""
    if not records:
        return
    _edit_record_note_by_index(len(records) - 1)


def on_records_right_click(event):
    """在记录区域右键：为鼠标所在行的那条记录添加/编辑说明（Alt+右键）"""
    try:
        global visible_record_indices
        if not visible_record_indices:
            return

        # 根据 y 坐标粗略判断是第几行
        height = records_label.winfo_height()
        line_count = len(visible_record_indices)
        if height <= 0 or line_count <= 0:
            return

        per_line = height / line_count
        idx = int(event.y / per_line)
        if idx < 0:
            idx = 0
        if idx >= line_count:
            idx = line_count - 1

        record_global_index = visible_record_indices[idx]
        _edit_record_note_by_index(record_global_index)
    except Exception as e:
        print(f"Error in on_records_right_click: {e}")


def on_records_right_click_handler(event):
    """处理记录区域的右键事件：Alt+右键编辑，普通右键显示菜单"""
    # 检查是否按下了 Alt 键（state 中的 0x20000 位表示 Alt）
    if event.state & 0x20000:  # Alt 键被按下
        # Alt + 右键：编辑记录说明
        on_records_right_click(event)
    else:
        # 普通右键：显示右键菜单
        show_context_menu(event)

# ======================
# 键盘监听
# ======================


def handle_f11_press():
    """处理F11按键：单击重置秒表，双击重置秒表和记录"""
    global key_timers, key_last_press
    current_time = time.time()
    last_time = key_last_press.get("F11", 0)
    
    # 取消之前的Timer（如果存在）
    if "F11" in key_timers:
        key_timers["F11"].cancel()
        del key_timers["F11"]
    
    # 检查是否是双击（300ms内）
    if current_time - last_time < DOUBLE_CLICK_DELAY:
        # 双击：重置秒表和记录
        key_last_press["F11"] = 0  # 重置，避免连续三次按键被误判
        root.after(0, reset_all)
    else:
        # 可能是单击，延迟执行
        key_last_press["F11"] = current_time
        timer = threading.Timer(SINGLE_CLICK_DELAY, lambda: root.after(0, reset_timer))
        key_timers["F11"] = timer
        timer.start()


def handle_f10_press():
    """处理F10按键：单击记录时间，双击显示/隐藏HUD"""
    global key_timers, key_last_press
    current_time = time.time()
    last_time = key_last_press.get("F10", 0)
    
    # 取消之前的Timer（如果存在）
    if "F10" in key_timers:
        key_timers["F10"].cancel()
        del key_timers["F10"]
    
    # 检查是否是双击（300ms内）
    if current_time - last_time < DOUBLE_CLICK_DELAY:
        # 双击：显示/隐藏HUD
        key_last_press["F10"] = 0  # 重置，避免连续三次按键被误判
        root.after(0, toggle_hud)
    else:
        # 可能是单击，延迟执行
        key_last_press["F10"] = current_time
        timer = threading.Timer(SINGLE_CLICK_DELAY, lambda: root.after(0, record_time))
        key_timers["F10"] = timer
        timer.start()


def keyboard_listener():
    """键盘监听器，带自动重启机制"""
    while True:
        try:
            # 清除之前的热键（如果存在）
            keyboard.unhook_all()

            # 重新注册所有热键
            keyboard.add_hotkey(HOTKEY_TOGGLE, toggle_timer)
            keyboard.add_hotkey(HOTKEY_RESET, handle_f11_press)  # F11：单击重置秒表，双击重置全部
            keyboard.add_hotkey(HOTKEY_RECORD, handle_f10_press)  # F10：单击记录时间，双击显示/隐藏HUD
            keyboard.add_hotkey(HOTKEY_EDIT_NOTE, lambda: root.after(0, add_record_note))  # F7：为最近一次记录添加说明
            keyboard.add_hotkey(HOTKEY_ZOOM_IN, zoom_in)
            keyboard.add_hotkey(HOTKEY_ZOOM_OUT, zoom_out)

            # 使用wait()阻塞，但如果出现问题会抛出异常
            keyboard.wait()
        except Exception as e:
            print(f"Keyboard listener error: {e}, restarting...")
            time.sleep(1)  # 等待1秒后重启
            # 循环继续，重新注册热键

# ======================
# 托盘
# ======================


def toggle_time_format():
    global config, fixed_width, fixed_height, last_display_text
    config["show_milliseconds"] = not config.get("show_milliseconds", False)
    save_config(show_milliseconds=config["show_milliseconds"])
    # 显示格式改变会影响最大宽度，重置缓存
    fixed_width = None
    fixed_height = None
    last_display_text = None
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
max_time_text = "99:59.999" if config.get(
    "show_milliseconds", False) else "99:59"
max_img = create_text_image(max_time_text, font_size=initial_font_size)
fixed_width = max_img.width
fixed_height = max_img.height
initial_img = create_text_image(format_time(0), font_size=initial_font_size,
                                target_width=fixed_width, target_height=fixed_height, align="center")
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

# 创建缩放百分比显示标签（初始隐藏）
zoom_label = tk.Label(
    main_frame,
    text="",
    bg="black",
    fg="#00FFAA",
    font=("Microsoft YaHei", 12, "bold"),
    bd=0,
    padx=0,
    pady=0,
    highlightthickness=0,
    anchor="w"  # 左对齐
)
# 初始不显示，等待缩放操作时显示

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
# 在记录区域右键：Alt+右键编辑记录说明，普通右键显示菜单
records_label.bind("<Button-3>", on_records_right_click_handler)

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
