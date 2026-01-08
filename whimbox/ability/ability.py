from whimbox.common.utils.utils import *
from whimbox.interaction.interaction_core import itt
from whimbox.common.utils.img_utils import *
from whimbox.common.utils.posi_utils import *
from whimbox.common.logger import logger
from whimbox.ability.cvar import *
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
from whimbox.common.utils.ui_utils import *
from whimbox.config.config import global_config

import time


class AbilityManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AbilityManager, cls).__new__(cls)
        return cls._instance


    def __init__(self):
        if self._initialized:
            return

        self.current_ability = None
        self.ability_keymap = None
        self.jump_ability = None
        self.battle_ability = None
        self._initialized = True


    def reinit(self):
        # 每次自动跑图开始前，都应该再次初始化一遍，避免用户手动调整了能力
        self.current_ability = None
        self.ability_keymap = None
        self.jump_ability = None
        self.battle_ability = None

    def get_current_ability(self):
        cap = itt.capture(anchor_posi=AreaAbilityButton.position)
        lower_white = [0, 0, 230]
        upper_white = [180, 60, 255]
        img = process_with_hsv_limit(cap, lower_white, upper_white)
        for icon in ability_hsv_icons:
            resize_icon = cv2.resize(icon.image, None, fx=0.73, fy=0.73, interpolation=cv2.INTER_LINEAR)
            rate = similar_img(img, resize_icon[:, :, 0], ret_mode=IMG_RATE)
            if rate > 0.8:
                return icon_name_to_ability_name.get(icon.name, None)
        return None

    def _get_ability_hsv_icon(self, center, cap):
        area = area_offset((-ability_icon_radius, -ability_icon_radius, ability_icon_radius, ability_icon_radius), offset=center)
        area = AnchorPosi(area[0], area[1], area[2], area[3], anchor=ANCHOR_CENTER)
        img = crop(cap, area)
        lower_white = [0, 0, 230]
        upper_white = [180, 60, 255]
        img = process_with_hsv_limit(img, lower_white, upper_white)
        return img


    def _check_jump_ability(self):
        cap = itt.capture()
        img = self._get_ability_hsv_icon(jump_ability_center, cap)
        for icon in jump_ability_hsv_icons:
            rate = similar_img(img, icon.image[:, :, 0], ret_mode=IMG_RATE)
            if rate > 0.8:
                ability_name = icon_name_to_ability_name.get(icon.name, None)
                if ability_name is not None:
                    self.jump_ability = ability_name
                    return True
        logger.error(f'unknown jump ability icon')
        return False


    def _check_ability_keymap(self):
        ability_keymap = {}
        cap = itt.capture()
        for i, center in enumerate(ability_icon_centers):
            img = self._get_ability_hsv_icon(center, cap)
            for icon in ability_hsv_icons:
                rate = similar_img(img, icon.image[:, :, 0], ret_mode=IMG_RATE)
                if rate > 0.8:
                    logger.debug(f'{icon.name} rate: {rate}')
                    ability_name = icon_name_to_ability_name.get(icon.name, None)
                    if ability_name is None:
                        logger.error(f'unknown ability icon: {icon.name}')
                    else:
                        ability_keymap[ability_name] = str(i+1)
                    break
        self.ability_keymap = ability_keymap
        return True


    def _change_ability_plan(self, ability_plan: int):
        # 切换能力配置方案，需要已经在能力配置界面
        AreaAbilityPlanChangeButton.click()
        time.sleep(0.2)
        if ability_plan == 1:
            AreaAbilityPlan1Button.click()
        elif ability_plan == 2:
            AreaAbilityPlan2Button.click()
        elif ability_plan == 3:
            AreaAbilityPlan3Button.click()
        else:
            raise(f'能力方案只能是123')
    

    def _set_ability(self, ability_name: str, ability_key: str):
        '''
        切换能力
        
        Args:
            ability_name: 能力名称，只能使用cvar中的ABILITY_NAME_XXX
            ability_key: 能力键位，只支持1~8和jump
        '''

        # 参数校验
        if ability_key != 'jump':
            if not is_int(ability_key):
                raise(f'ability_key is not a int: {ability_key}')
            ability_index = int(ability_key) - 1
            if ability_index < 0 or ability_index >= len(ability_icon_centers):
                raise(f'ability_key can only 1~8, but got {ability_key}')

        # 获取当前能力配置
        if self.jump_ability is None:
            self._check_jump_ability()
        if self.ability_keymap is None:
            self._check_ability_keymap()

        # 检查当前能力配置是否已经满足要求
        if ability_key == 'jump':
            if self.jump_ability == ability_name:
                ui_control.goto_page(page_main)
                return True
        else:
            if self.ability_keymap.get(ability_name, None) == ability_key:
                ui_control.goto_page(page_main)
                return True

        # 开始配置能力
        if ability_key == 'jump':
            target_ability_icon_center = jump_ability_center
        else:
            target_ability_icon_center = ability_icon_centers[ability_index]
        itt.move_and_click(target_ability_icon_center, anchor=ANCHOR_CENTER)
        time.sleep(0.2)
        # 向下滚动，寻找指定的ability_name
        res = scroll_find_click(AreaAbilityChange, ability_name, click_offset=(80, 80))
        if res:
            itt.appear_then_click(ButtonAbilitySave)
            if ability_key == 'jump':
                self.jump_ability = ability_name
            else:
                self.ability_keymap[ability_name] = ability_key

        ui_control.goto_page(page_main)
        return res

    def get_ability_keybind(self, ability_index: str):
        if ability_index == '1':
            return keybind.KEYBIND_ABILITY_1
        elif ability_index == '2':
            return keybind.KEYBIND_ABILITY_2
        elif ability_index == '3':
            return keybind.KEYBIND_ABILITY_3
        elif ability_index == '4':
            return keybind.KEYBIND_ABILITY_4
        elif ability_index == '5':
            return keybind.KEYBIND_ABILITY_5
        elif ability_index == '6':
            return keybind.KEYBIND_ABILITY_6
        elif ability_index == '7':
            return keybind.KEYBIND_ABILITY_7
        elif ability_index == '8':
            return keybind.KEYBIND_ABILITY_8
        else:
            raise(f'ability_index can only 1~8, but got {ability_index}')

    def change_ability(self, ability_name: str):
        # 如果当前能力已经符合，就直接返回
        if self.current_ability == ability_name:
            return True
        self.current_ability = self.get_current_ability()
        if self.current_ability == ability_name:
            return True
        # 检查能力配置是否已初始化
        if self.ability_keymap is None:
            ui_control.goto_page(page_ability)
            self._check_ability_keymap()
        # 检查目标能力是否已配置
        key = self.ability_keymap.get(ability_name, None)
        if key is None:
            # 如果没配置，根据配置文件，配置到对应的方案和键位
            ability_plan = global_config.get_int('Game', 'ability_plan')
            self._change_ability_plan(ability_plan)
            itt.wait_until_stable(threshold=0.99)
            self._check_ability_keymap()
            key = self.ability_keymap.get(ability_name, None)
            if key is None:
                ability_key = str(global_config.get_int('Game', 'ability_key'))
                if self._set_ability(ability_name, ability_key):
                    key = ability_key
        
        key = self.get_ability_keybind(key)

        ui_control.goto_page(page_main)
        if key:
            itt.key_press(key)
            self.current_ability = ability_name
            itt.delay(0.5, comment="等待能力切换完成")
            return True
        else:
            return False
        

ability_manager = AbilityManager()


if __name__ == "__main__":
    # CV_DEBUG_MODE = True
    # ability_manager.change_ability(ABILITY_NAME_INSECT)
    print(ability_manager.get_current_ability())
    # ability_manager._check_jump_ability()
    # ability_manager._check_ability_keymap()
    # print(ability_manager.ability_keymap)
