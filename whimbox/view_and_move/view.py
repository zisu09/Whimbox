from whimbox.common.logger import logger
from whimbox.map.map import nikki_map
from whimbox.common.timer_module import TimeoutTimer
from whimbox.view_and_move.utils import *
from whimbox.interaction.interaction_core import itt
from whimbox.common.cvars import get_current_stop_flag
import time

def direct_cview(angel):
    px = angle2movex(angel)
    itt.move_to([px, 0], relative=True)


def get_safe_rotation(last_angle=None, offset=5):
    """多取几次视角角度，避免抖动"""
    get_timeout = TimeoutTimer(0.4)
    angle_list = []
    if last_angle is None:
        angle_list.append(nikki_map.get_rotation())
    else:
        angle_list.append(last_angle)
    succ_times = 0
    while 1:
        if get_timeout.istimeout():
            logger.trace(f"get_rotation break due to timeout")
            break
        pt = time.time()
        angle_list.append(nikki_map.get_rotation())
        time_cost = round(time.time()-pt,5)

        if abs(calculate_delta_angle(angle_list[-1], angle_list[-2])) < offset:
            succ_times += 1
        else:
            succ_times = 0

        if time_cost < 0.04:
            time.sleep(0.04-time_cost)
            if succ_times >= 3:
                # logger.trace(f"get_rotation break: succ >=2")
                break
        else:
            if succ_times >= 1:
                # logger.trace(f"get_rotation break: succ")
                break
    return angle_list[-1]


def reset_view_rotation_ratio():
    config["view_rotation_ratio"] = 1

def calibrate_view_rotation_ratio(offset=5):
    """校准视角旋转比例"""
    if config["view_rotation_ratio"] != 1:
        return
    stop_flag = get_current_stop_flag()
    while not stop_flag.is_set():
        cangle = get_safe_rotation(offset=offset)
        direct_cview(90)
        time.sleep(0.3)
        tangle = get_safe_rotation(offset=offset)
        dangle = calculate_delta_angle(cangle, tangle)
        if abs(90-dangle) < offset:
            break 
        if dangle == 0:
            continue
        config["view_rotation_ratio"] = 90 / dangle * config["view_rotation_ratio"]


def change_view_to_angle(tangle, offset:float=5, use_last_rotation=False):
    """转动视角到指定角度"""
    if use_last_rotation:
        cangle = get_safe_rotation(last_angle=nikki_map.rotation, offset=offset)
    else:
        cangle = get_safe_rotation(offset=offset)
    dangle = calculate_delta_angle(cangle, tangle)
    if abs(dangle) > offset:
        direct_cview(dangle)


if __name__ == "__main__":
    from whimbox.common.utils.ui_utils import back_to_page_main
    nikki_map.reinit_smallmap()
    back_to_page_main()
    calibrate_view_rotation_ratio()
    print(f"view_rotation_ratio: {config['view_rotation_ratio']}")
    print(nikki_map.get_rotation())
    direct_cview(90)
    time.sleep(0.5)
    print(nikki_map.get_rotation())
    direct_cview(45)
    time.sleep(0.5)
    print(nikki_map.get_rotation())