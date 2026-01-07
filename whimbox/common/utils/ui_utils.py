'''通用的游戏UI操作工具'''

from whimbox.ui.template.img_manager import GameImg, ImgIcon
from whimbox.ui.template.button_manager import Button
from whimbox.ui.template.text_manager import Text
from whimbox.ui.template.posi_manager import Area
from whimbox.interaction.interaction_core import itt
from whimbox.common.utils.img_utils import *
from whimbox.common.utils.posi_utils import *
from whimbox.ui.ui_assets import *
from whimbox.common.keybind import keybind
from whimbox.common.cvars import get_current_stop_flag
import time
from whimbox.common.logger import logger


def find_game_img(game_img: GameImg, cap, threshold, scale=0.5):
    # 准备需要匹配的两张图片
    template = game_img.raw_image
    if template.shape[2] == 4:
        template_rgb = template[:, :, :3]
        alpha = template[:, :, 3]
        mask = (alpha > 128).astype(np.uint8) * 255  # 透明区域设为0，不参与检测
    else:
        template_rgb = template
        mask = None

    if scale:
        # 为什么INTER_LINEAR，因为如果用INTER_NEAREST，有些图片里太细的线条就会被忽略（比如纯真丝线），导致相似度大幅下降
        template_rgb = cv2.resize(template_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        if mask is not None:
            mask = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)

    if CV_DEBUG_MODE:
        # 将template_rgb的mask区域显示为黑色，用cv2显示出来
        template_show = template_rgb.copy()
        template_show[mask == 0] = 0
        cv2.imshow("template", template_show)
        cv2.waitKey(0)
    
    # 模板匹配
    res = cv2.matchTemplate(cap, template_rgb, cv2.TM_CCOEFF_NORMED, mask=mask)


    # 找到最大匹配位置
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    th, tw = template_rgb.shape[:2]
    top_left = max_loc
    bottom_right = (top_left[0] + tw, top_left[1] + th)

    if max_val >= threshold:
        logger.trace('imgname: ' + game_img.name + ' matching_rate: ' + str(max_val))

    if CV_DEBUG_MODE:
        # 在目标图上绘制矩形
        print(f"max_val: {max_val}, threshold: {threshold}")
        cap_copy = cap.copy()
        cv2.rectangle(cap_copy, top_left, bottom_right, (0,255,0), 3)
        cv2.imshow("Detected", cap_copy)
        cv2.waitKey(0)
    
    if max_val < threshold:
        return None

    box = [top_left[0], top_left[1], bottom_right[0], bottom_right[1]]
    return box


def scroll_find_click(area: Area, target, threshold=0, hsv_limit=None, scale=0, str_match_mode=0, click_offset=(0, 0), need_scroll=True) -> bool:
    '''
    在指定的区域内滚动，寻找并点击目标

    Args:
        area: 目标区域
        target: 寻找的目标，ImgIcon或GameImg或str
        threshold: 相似度阈值, 用于ImgIcon和GameImg
        hsv_limit: hsv上下限，用于ImgIcon和str，如([0, 0, 230], [180, 60, 255])
        scale: target的缩放比例，用于ImgIcon或GameImg
        str_match_mode: 字符串匹配模式，0为完全匹配，1为包含匹配
        click_offset: 点击偏移量，tuple(x, y)
        need_scroll: 是否需要滚动，默认True
    
    Returns:
        bool: 是否找到目标
    '''
    box = None
    cap = itt.capture(anchor_posi = area.position)
    is_first_time = True
    while True:
        stop_flag = get_current_stop_flag()
        if stop_flag.is_set():
            return False
        if isinstance(target, ImgIcon):
            target_img = target.image
            if target.hsv_limit:
                hsv_limit = target.hsv_limit
            if hsv_limit:
                if scale:
                    target_img = cv2.resize(target_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
                if not target.hsv_limit:
                    target_img = target_img[:, :, 0]
                cap_hsv = process_with_hsv_limit(cap, hsv_limit[0], hsv_limit[1])
                rate, loc = similar_img(cap_hsv, target_img, ret_mode=IMG_RECT)
            else:
                if scale:
                    target_img = cv2.resize(target_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
                rate, loc = similar_img(cap, target_img, ret_mode=IMG_RECT)

            if target.is_print_log(rate >= threshold):
                logger.trace('imgname: ' + target.name + ' matching_rate: ' + str(rate))

            if rate > threshold:
                th, tw = target_img.shape[:2]
                top_left = loc
                bottom_right = (top_left[0] + tw, top_left[1] + th)
                if CV_DEBUG_MODE:
                    print(f"rate: {rate}, threshold: {threshold}")
                    cap_copy = cap.copy()
                    cv2.rectangle(cap_copy, top_left, bottom_right, (0, 255, 0), 2)
                    cv2.imshow("Detected", cap_copy)
                    cv2.waitKey(0)
                box = [top_left[0], top_left[1], bottom_right[0], bottom_right[1]]
                break

        elif isinstance(target, GameImg):
            box = find_game_img(target, cap, threshold, scale)
            if box:
                break
        
        elif isinstance(target, str):
            text_box_dict = itt.ocr_and_detect_posi(area, hsv_limit=hsv_limit)
            if str_match_mode == 0:
                if target in text_box_dict:
                    box = text_box_dict[target]
                    break
            elif str_match_mode == 1:
                for text, text_box in text_box_dict.items():
                    if target in text:
                        box = text_box
                        break
                if box is not None:
                    break
        
        else:
            raise Exception(f"不支持的target类型: {type(target)}")


        if need_scroll:
            # 如果第一次没找到目标，就先把画面滚到顶，再开始寻找
            if is_first_time:
                logger.info(f"第一次没找到目标，先把画面滚到顶")
                cap = scroll_to_top(area)
                is_first_time = False
            else:
                # 如果没找到目标，就把鼠标移到area的右下角，向下滚动
                # todo: 支持expand，不过暂时没什么关系
                scroll_posi = (area.position.x2, area.position.y2)
                itt.move_to(scroll_posi, anchor=area.position.anchor)
                itt.middle_scroll(-15)
                time.sleep(0.2)

                # 如果画面不再变化，说明滚到底了
                new_cap = itt.capture(anchor_posi = area.position)
                rate = similar_img(cap, new_cap)
                if rate > 0.99:
                    break
                else:
                    cap = new_cap
        else:
            break
        
    if box:
        time.sleep(0.3)
        area.click(target_box=box, offset=click_offset)
        return True
    else:
        return False


def scroll_to_top(area: Area):
    # 鼠标移到area的右下角
    # todo: 支持expand，不过暂时没什么关系
    scroll_posi = (area.position.x2, area.position.y2)
    itt.move_to(scroll_posi, anchor=area.position.anchor)
    last_cap = itt.capture(anchor_posi=area.position)
    while True:
        stop_flag = get_current_stop_flag()
        if stop_flag.is_set():
            return last_cap
        itt.middle_scroll(15)
        time.sleep(0.2)
        new_cap = itt.capture(anchor_posi=area.position)
        rate = similar_img(last_cap, new_cap)
        if rate > 0.99:
            return new_cap
        last_cap = new_cap

    
def wait_until_appear_then_click(obj, retry_time=3):
    while retry_time > 0:
        if isinstance(obj, Button):
            if itt.appear_then_click(obj):
                return True
        elif isinstance(obj, Text):
            if itt.appear_then_click(obj):
                return True
        else:
            return False
        retry_time -= 1
        time.sleep(1)
    return False


def wait_until_appear(obj, area=None, retry_time=3):
    while retry_time > 0:
        if area:
            cap = itt.capture(anchor_posi=area.position)
        else:
            cap = None
        if isinstance(obj, ImgIcon):
            if itt.get_img_existence(obj, cap=cap):
                return True
        elif isinstance(obj, Text):
            if itt.get_text_existence(obj, cap=cap):
                return True
        else:
            return False
        retry_time -= 1
        time.sleep(1)
    return False


def back_to_page_main():
    # 让UI返回到主界面
    stop_flag = get_current_stop_flag()
    while not stop_flag.is_set():
        itt.wait_until_stable(threshold=0.95)
        if itt.get_img_existence(IconDungeonFeature):
            itt.key_press(keybind.KEYBIND_BACK)
        elif itt.get_img_existence(IconPageMainFeature):
            break
        else:
            itt.key_press('esc')

def skip_to_page_main():
    # 采集时，如果遇到没有的东西，会自动弹出获取窗口，不断按f跳过直到回到主界面
    stop_flag = get_current_stop_flag()
    while not stop_flag.is_set():
        time.sleep(0.5)
        if not itt.get_img_existence(IconPageMainFeature):
            itt.key_press(keybind.KEYBIND_INTERACTION)
        else:
            break

def skip_dialog():
    stop_flag = get_current_stop_flag()
    while not stop_flag.is_set():
        time.sleep(0.5)
        if itt.get_img_existence(IconSkipDialog):
            itt.key_press(keybind.KEYBIND_INTERACTION)
        else:
            # 防止遇到什么奇怪的情况，退出前再做一次检查
            time.sleep(0.5)
            if not itt.get_img_existence(IconSkipDialog):
                break
            else:
                itt.key_press(keybind.KEYBIND_INTERACTION)

def skip_get_award():
    if wait_until_appear(IconClickSkip):
        itt.delay(1, comment="不加延迟，有些电脑就是不行")
        itt.key_press(keybind.KEYBIND_INTERACTION)
        return True
    else:
        return False
        
            
if __name__ == "__main__":
    # while True:
    #     print(itt.get_img_existence(IconDungeonFeature, ret_mode=IMG_RATE))
    #     time.sleep(1)
    # back_to_page_main()
    CV_DEBUG_MODE = True
    from whimbox.ui.material_icon_assets import material_icon_dict
    # material_name = "纯真丝线"
    # material_name = "玉簪蚱蜢"
    # target = material_icon_dict[material_name]["icon"]
    # scroll_find_click(AreaBigMapMaterialSelect, target, threshold=0.8, scale=0.45)
    # cap = itt.capture(posi=AreaDigItemSelect.position)
    # find_game_img(target, cap, threshold=0.7, scale=0.46)
    # cap = itt.capture(posi=AreaBigMapMaterialSelect.position)
    # find_game_img(target, cap, threshold=0.9, scale=0.45)

    # hsv_limit = [np.array([0, 0, 100]), np.array([180, 60, 255])]
    # # scroll_find_click(AreaDigMainTypeSelect, IconMaterialTypeMonster, threshold=0.85, hsv_limit=hsv_limit, scale=1.233)
    # scroll_find_click(AreaDigSubTypeSelect, IconMaterialTypeInsect, threshold=0.85, hsv_limit=hsv_limit, scale=0.83)

    # scroll_find_click(AreaBlessHuanjingLevelsSelect, "翻滚", str_match_mode=1)
    # scroll_find_click(AreaEscEntrances, "美鸭梨挖掘")
    scroll_find_click(AreaItemQuickList, IconItemPlaceable, scale=1.05, threshold=IconItemPlaceable.threshold, need_scroll=False)

    