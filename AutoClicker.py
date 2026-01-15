import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import keyboard
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import json
import os
from pynput import mouse

# ======================
# 配置
# ======================
CONFIG_FILE = "autoclicker_config.json"
HOTKEY_START_STOP = "F9"  # 开始/停止自动点击

# ======================
# 状态
# ======================
is_clicking = False
click_thread = None
click_interval = 1.0  # 默认1秒
click_x = 0
click_y = 0
keyboard_listener_running = False
keyboard_hook = None
capturing_position = False  # 是否正在等待捕获鼠标点击位置
mouse_listener = None  # 鼠标监听器

# ======================
# 配置读写
# ======================


def load_config():
    """加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg
        except:
            pass
    return {
        "interval": 1.0,
        "x": 0,
        "y": 0,
        "window_x": 600,
        "window_y": 300
    }


def save_config(**kwargs):
    """保存配置"""
    global config
    config.update(kwargs)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")


config = load_config()
click_interval = config.get("interval", 1.0)
click_x = config.get("x", 0)
click_y = config.get("y", 0)

# ======================
# 自动点击逻辑
# ======================


def auto_click_loop():
    """自动点击循环"""
    global is_clicking, click_interval, click_x, click_y
    mouse_controller = mouse.Controller()
    
    while is_clicking:
        try:
            # 移动到指定位置并点击
            mouse_controller.position = (click_x, click_y)
            mouse_controller.click(mouse.Button.left, 1)
            
            # 等待指定间隔
            time.sleep(click_interval)
        except Exception as e:
            print(f"Error in auto_click_loop: {e}")
            break


def start_clicking():
    """开始自动点击"""
    global is_clicking, click_thread, click_x, click_y
    
    if is_clicking:
        return
    
    # 检查坐标是否有效
    if click_x < 0 or click_y < 0:
        try:
            messagebox.showwarning("警告", "请先设置点击位置！")
        except:
            pass  # 窗口关闭时忽略消息框
        return
    
    if click_interval <= 0:
        try:
            messagebox.showwarning("警告", "点击间隔必须大于0！")
        except:
            pass  # 窗口关闭时忽略消息框
        return
    
    is_clicking = True
    click_thread = threading.Thread(target=auto_click_loop, daemon=True)
    click_thread.start()
    try:
        update_ui()
    except:
        pass  # 窗口关闭时忽略 UI 更新


def stop_clicking():
    """停止自动点击"""
    global is_clicking
    is_clicking = False
    try:
        update_ui()
    except:
        pass  # 窗口关闭时忽略 UI 更新


def toggle_clicking():
    """切换点击状态"""
    if is_clicking:
        stop_clicking()
    else:
        start_clicking()

# ======================
# 键盘监听
# ======================


def safe_callback(func):
    """安全的回调包装器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error in callback {func.__name__}: {e}")
    return wrapper


def keyboard_event_handler(event):
    """全局键盘事件处理函数"""
    try:
        if event.event_type == keyboard.KEY_DOWN:
            # F9 键的名称可能是 'f9' 或 'F9'
            key_name = event.name.lower() if event.name else ""
            if key_name == HOTKEY_START_STOP.lower():
                # 确保在主线程中执行，即使窗口已关闭也能工作
                try:
                    # 尝试使用 after_idle
                    root.after_idle(toggle_clicking)
                except:
                    try:
                        # 如果失败，尝试使用 after(0)
                        root.after(0, toggle_clicking)
                    except:
                        # 如果 root 窗口不存在，直接调用（在后台线程中）
                        # 但需要确保 toggle_clicking 是线程安全的
                        toggle_clicking()
    except Exception as e:
        print(f"Error in keyboard_event_handler: {e}")


def keyboard_listener():
    """键盘监听器"""
    global keyboard_listener_running, keyboard_hook
    
    keyboard_listener_running = True
    
    while keyboard_listener_running:
        try:
            # 注册全局键盘钩子
            keyboard_hook = keyboard.hook(keyboard_event_handler)
            
            # 保持运行
            while keyboard_listener_running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Keyboard listener error: {e}, restarting...")
            time.sleep(2)


# ======================
# GUI
# ======================


def update_ui():
    """更新UI状态"""
    try:
        if is_clicking:
            status_label.config(text="状态: 运行中", fg="#FF0000")
            start_btn.config(state="disabled")
            stop_btn.config(state="normal")
        else:
            status_label.config(text="状态: 已停止", fg="#FF6B6B")
            start_btn.config(state="normal")
            stop_btn.config(state="disabled")
    except:
        pass  # 窗口关闭时忽略 UI 更新
    # 更新托盘菜单（即使窗口关闭也要更新）
    update_tray_menu()


def on_interval_change(*args):
    """点击间隔改变"""
    global click_interval
    try:
        value = float(interval_var.get())
        if value > 0:
            click_interval = value
            save_config(interval=value)
    except:
        pass


def on_x_change(*args):
    """X坐标改变"""
    global click_x
    try:
        value = int(x_var.get())
        if value >= 0:
            click_x = value
            save_config(x=value)
    except:
        pass


def on_y_change(*args):
    """Y坐标改变"""
    global click_y
    try:
        value = int(y_var.get())
        if value >= 0:
            click_y = value
            save_config(y=value)
    except:
        pass


def on_mouse_click(x, y, button, pressed):
    """鼠标点击事件处理（用于捕获位置）"""
    global capturing_position, click_x, click_y, mouse_listener
    
    if not capturing_position:
        return True  # 继续监听
    
    if pressed and button == mouse.Button.left:
        # 捕获左键点击位置
        click_x = int(x)
        click_y = int(y)
        capturing_position = False
        
        # 停止监听器
        try:
            if mouse_listener:
                mouse_listener.stop()
                mouse_listener = None
        except:
            pass
        
        # 更新UI（在主线程中执行）
        root.after(0, lambda: update_captured_position(click_x, click_y))
        return False  # 停止监听器
    
    return True  # 继续监听


def update_captured_position(x, y):
    """更新捕获的位置到UI"""
    global click_x, click_y
    try:
        x_var.set(str(x))
        y_var.set(str(y))
        save_config(x=x, y=y)
        capture_btn.config(text="捕获下一次鼠标点击位置", state="normal")
        # 在界面上显示捕获的位置信息
        if 'capture_info_label' in globals():
            capture_info_label.config(text=f"已捕获位置: ({x}, {y})", fg="#00AA00")
    except Exception as e:
        capture_btn.config(text="捕获下一次鼠标点击位置", state="normal")
        if 'capture_info_label' in globals():
            capture_info_label.config(text=f"更新位置失败: {e}", fg="#FF0000")


def capture_position():
    """开始捕获下一次鼠标点击位置"""
    global capturing_position, mouse_listener
    
    if capturing_position:
        # 如果正在捕获，取消捕获
        capturing_position = False
        try:
            if mouse_listener:
                mouse_listener.stop()
                mouse_listener = None
        except:
            pass
        capture_btn.config(text="捕获下一次鼠标点击位置", state="normal")
        if 'capture_info_label' in globals():
            capture_info_label.config(text="", fg="#888888")
        return
    
    try:
        capturing_position = True
        capture_btn.config(text="等待鼠标点击... (再次点击按钮取消)", state="normal")
        
        # 在界面上显示提示
        if 'capture_info_label' in globals():
            capture_info_label.config(text="请点击您想要自动点击的位置...", fg="#FFAA00")
        
        # 创建鼠标监听器（在后台线程中运行）
        mouse_listener = mouse.Listener(on_click=on_mouse_click)
        mouse_listener.start()
    except Exception as e:
        capturing_position = False
        capture_btn.config(text="捕获下一次鼠标点击位置", state="normal")
        if 'capture_info_label' in globals():
            capture_info_label.config(text=f"启动捕获失败: {e}", fg="#FF0000")


def on_closing():
    """窗口关闭事件"""
    global capturing_position, mouse_listener
    # 注意：不要停止键盘监听器，保持 F9 快捷键可用
    capturing_position = False
    
    try:
        if mouse_listener:
            mouse_listener.stop()
            mouse_listener = None
    except:
        pass
    
    save_config(window_x=root.winfo_x(), window_y=root.winfo_y())
    root.withdraw()  # 隐藏窗口而不是关闭


def show_window():
    """显示窗口"""
    root.deiconify()
    root.lift()
    root.focus_force()


def on_exit():
    """退出程序"""
    global is_clicking, keyboard_listener_running, keyboard_hook, tray_icon, capturing_position, mouse_listener
    is_clicking = False
    keyboard_listener_running = False
    capturing_position = False
    
    try:
        if mouse_listener:
            mouse_listener.stop()
            mouse_listener = None
    except:
        pass
    
    try:
        if keyboard_hook:
            keyboard.unhook(keyboard_hook)
    except:
        pass
    
    try:
        keyboard.unhook_all()
    except:
        pass
    
    try:
        tray_icon.stop()
    except:
        pass
    
    root.quit()


# ======================
# 系统托盘
# ======================


def create_tray_icon():
    """创建系统托盘图标"""
    global tray_icon
    # 使用透明背景
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # 绘制一个更粗的空心圆形图标（粉红色）
    draw.ellipse((10, 10, 54, 54), outline="#FF6B9D", width=6)
    
    status_text = "开始点击" if not is_clicking else "停止点击"
    
    menu = (
        item("显示窗口", show_window),
        item(status_text, lambda: root.after(0, toggle_clicking)),
        item("退出", on_exit),
    )
    
    tray_icon = pystray.Icon("AutoClicker", image, "鼠标自动点击工具", menu)
    tray_icon.run()


def update_tray_menu():
    """更新托盘菜单"""
    global tray_icon
    try:
        if tray_icon is None:
            return
        
        status_text = "开始点击" if not is_clicking else "停止点击"
        
        menu = (
            item("显示窗口", show_window),
            item(status_text, lambda: root.after(0, toggle_clicking)),
            item("退出", on_exit),
        )
        
        tray_icon.menu = pystray.Menu(*menu)
        tray_icon.update_menu()
    except Exception as e:
        # 忽略托盘菜单更新错误，避免影响主程序
        pass


# ======================
# 主窗口
# ======================

root = tk.Tk()
root.title("鼠标自动点击工具")
root.geometry(f"400x380+{config.get('window_x', 600)}+{config.get('window_y', 300)}")
root.resizable(False, False)

# 设置窗口关闭事件
root.protocol("WM_DELETE_WINDOW", on_closing)

# 主框架
main_frame = ttk.Frame(root, padding="20")
main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

# 状态标签
status_label = tk.Label(
    main_frame,
    text="状态: 已停止",
    font=("Microsoft YaHei", 12, "bold"),
    fg="#FF6B6B"
)
status_label.pack(pady=(0, 10))

# 捕获位置信息标签
capture_info_label = tk.Label(
    main_frame,
    text="",
    font=("Microsoft YaHei", 9),
    fg="#888888"
)
capture_info_label.pack(pady=(0, 10))

# 点击间隔设置
interval_frame = ttk.Frame(main_frame)
interval_frame.pack(fill=tk.X, pady=5)

ttk.Label(interval_frame, text="点击间隔(秒):", width=15).pack(side=tk.LEFT)
interval_var = tk.StringVar(value=str(click_interval))
interval_var.trace("w", on_interval_change)
interval_entry = ttk.Entry(interval_frame, textvariable=interval_var, width=15)
interval_entry.pack(side=tk.LEFT, padx=5)

# X坐标设置
x_frame = ttk.Frame(main_frame)
x_frame.pack(fill=tk.X, pady=5)

ttk.Label(x_frame, text="X坐标:", width=15).pack(side=tk.LEFT)
x_var = tk.StringVar(value=str(click_x))
x_var.trace("w", on_x_change)
x_entry = ttk.Entry(x_frame, textvariable=x_var, width=15)
x_entry.pack(side=tk.LEFT, padx=5)

# Y坐标设置
y_frame = ttk.Frame(main_frame)
y_frame.pack(fill=tk.X, pady=5)

ttk.Label(y_frame, text="Y坐标:", width=15).pack(side=tk.LEFT)
y_var = tk.StringVar(value=str(click_y))
y_var.trace("w", on_y_change)
y_entry = ttk.Entry(y_frame, textvariable=y_var, width=15)
y_entry.pack(side=tk.LEFT, padx=5)

# 捕获位置按钮
capture_btn = ttk.Button(
    main_frame,
    text="捕获下一次鼠标点击位置",
    command=capture_position
)
capture_btn.pack(pady=10)

# 控制按钮
btn_frame = ttk.Frame(main_frame)
btn_frame.pack(pady=20)

start_btn = ttk.Button(
    btn_frame,
    text="开始（F9）",
    command=start_clicking,
    width=15
)
start_btn.pack(side=tk.LEFT, padx=5)

stop_btn = ttk.Button(
    btn_frame,
    text="停止（F9）",
    command=stop_clicking,
    width=15,
    state="disabled"
)
stop_btn.pack(side=tk.LEFT, padx=5)

# 提示信息
info_label = tk.Label(
    main_frame,
    text=f"按 {HOTKEY_START_STOP} 键可快速开始/停止",
    font=("Microsoft YaHei", 9),
    fg="#888888"
)
info_label.pack(pady=(10, 20))

# ======================
# 启动线程
# ======================

# 初始化全局变量
tray_icon = None

# 初始化UI
update_ui()

# 启动后台线程
threading.Thread(target=create_tray_icon, daemon=True).start()
threading.Thread(target=keyboard_listener, daemon=True).start()

# 定期更新托盘菜单
def update_tray_menu_loop():
    if tray_icon:
        update_tray_menu()
    root.after(1000, update_tray_menu_loop)

update_tray_menu_loop()

root.mainloop()
