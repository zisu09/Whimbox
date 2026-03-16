from whimbox.common.cvars import *
from whimbox.ui.ui import ui_control
from whimbox.ui.page_assets import *
from whimbox.interaction.interaction_core import itt
from whimbox.common.utils.img_utils import *
from whimbox.ui.material_icon_assets import material_icon_dict
from whimbox.common.utils.ui_utils import *
from whimbox.map.map import nikki_map, MINIMAP_RADIUS
from whimbox.view_and_move.utils import *
from whimbox.ability.cvar import *

import time

material_type_icon_dict = {
    "plant": IconMaterialTypePlant,
    "animal": IconMaterialTypeAnimal,
    "insect": IconMaterialTypeInsect,
    "fish": IconMaterialTypeFish,
    "monster": IconMaterialTypeMonster,
}

material_type_to_ability_name = {
    "animal": ABILITY_NAME_ANIMAL,
    "insect": ABILITY_NAME_INSECT,
}

class Track:
    def __init__(self):
        self.tracking_material = None
        self.last_track_posi = None

    def change_tracking_material(self, material_name: str):
        '''
        大地图追踪指定材料，用于在小地图上显示附近的材料点位，后续自动寻路去获取
        '''

        if self.tracking_material == material_name:
            return
        
        if material_name not in material_icon_dict:
            raise Exception(f"不支持追踪{material_name}")
        material_info = material_icon_dict[material_name]
        if not material_info["track"]:
            raise Exception(f"不支持追踪{material_name}")

        material_icon = material_info['icon']
        material_type = material_info['type']
        if material_type not in material_type_icon_dict:
            raise Exception(f"暂不支持追踪{material_type}类型的材料")
        material_type_icon = material_type_icon_dict[material_type]

        # 打开材料追踪窗口
        ui_control.goto_page(page_bigmap)
        itt.appear_then_click(IconUIBigmap)
        itt.wait_until_stable()

        # 选择材料类别
        result = scroll_find_click(
            AreaBigMapMaterialTypeSelect, 
            material_type_icon, 
            threshold=0.75, 
            hsv_limit=([0, 0, 230], [180, 60, 255]))
        if not result:
            raise Exception("材料类别选择失败")
        
        # 选择材料
        time.sleep(0.2) # 等待类别切换完成
        result = scroll_find_click(
            AreaBigMapMaterialSelect, 
            material_icon, 
            threshold=0.8, 
            scale=0.45, 
            scroll_distance=10)
        if not result:
            raise Exception("材料选择失败")

        # 点击“精确追踪”
        time.sleep(0.2) # 等待一会，避免识别到上一个素材的追踪按钮
        button_text = itt.ocr_single_line(AreaBigMapMaterialTrackConfirm, padding=50)
        if button_text == "精确追踪":
            AreaBigMapMaterialTrackConfirm.click()
            itt.wait_until_stable()
            self.tracking_material = material_name
            ui_control.goto_page(page_main)
            return True
        elif button_text == "取消追踪":
            self.tracking_material = material_name
            itt.key_press('esc')
            ui_control.goto_page(page_main)
            return True
        else:
            raise Exception("该材料未开启精确追踪")

    def get_material_track_degree(self):
        '''根据小地图，计算材料与玩家之间的角度'''
        cap = itt.capture()
        minimap_img = nikki_map._get_minimap(cap, MINIMAP_RADIUS)
        lower = [13, 90, 160]
        upper = [15, 200, 255]
        minimap_hsv = process_with_hsv_limit(minimap_img, lower, upper)
        # 在小地图中心绘制一个圆，来遮住箭头
        cv2.circle(minimap_hsv, (MINIMAP_RADIUS, MINIMAP_RADIUS), 10, (255, 255, 255), -1)
        minimap_blur = cv2.GaussianBlur(minimap_hsv, (3, 3), 1)
        if CV_DEBUG_MODE:
            cv2.imshow("minimap_blur", minimap_blur)
            cv2.waitKey(1)

        circles = cv2.HoughCircles(
            minimap_blur,
            cv2.HOUGH_GRADIENT,
            dp=1,          # 累加器分辨率（可调 1.0~1.5）
            minDist=10,      # 圆心最小间距，建议≈ 2*minRadius - 些许
            param1=60,      # Canny高阈值
            param2=8,       # 累加器阈值，越小越容易出圆（可调 8~18）
            minRadius=14,
            maxRadius=18
        )
        
        if circles is not None:
            minimap_center = (MINIMAP_RADIUS, MINIMAP_RADIUS)
            min_dist = 99999
            track_circle = None
            for x, y, r in circles[0, :]:
                # 如果之前没有追踪，就追踪最近的一个，否则追踪之前的点
                if self.last_track_posi is None:
                    dist = euclidean_distance(minimap_center, (x, y))
                    track_circle = (x, y, r)
                else:
                    dist = euclidean_distance(self.last_track_posi, (x, y))
                if dist < min_dist:
                    min_dist = dist
                    track_circle = (x, y, r)
            self.last_track_posi = track_circle[0:2]

            if CV_DEBUG_MODE:
                print(f"dist: {euclidean_distance(minimap_center, self.last_track_posi)}")
                x, y, r = np.uint16(np.around(track_circle))
                cv2.circle(minimap_img, (x, y), r, (0, 0, 255), 2)
                cv2.circle(minimap_img, (x, y), 2, (0, 0, 255), 3)
                cv2.imshow("minimap_img", minimap_img)
                cv2.waitKey(1)
            
            # 只追踪身边的材料，避免跑去下一个采集点或者很远的采集点（按布布袜虫的敏感距离推算）
            track_dist = euclidean_distance(minimap_center, track_circle[0:2])
            if track_dist > 30:
                self.last_track_posi = None
                return None
            else:
                degree = calculate_posi2degree(minimap_center, track_circle[0:2])
                return degree
        return None
    
    def is_ability_active(self):
        '''
        判断能力是否激活，通过判断能力按钮外圈是否发光，来判断是否可以使用能力了
        '''
        img = itt.capture(anchor_posi=AreaAbilityButton.position)
        lower = [0, 80, 200]
        upper = [30, 110, 255]
        px_count = count_px_with_hsv_limit(img, lower, upper)
        # print(f"px_count: {px_count}")
        if px_count > 200:
            return True
        return False

    def clear_last_track_posi(self):
        self.last_track_posi = None

material_track = Track()

if __name__ == "__main__":
    CV_DEBUG_MODE = True
    material_track.change_tracking_material("美甲金龟")
    # while True:
    #     print(material_track.get_material_track_degree())
    #     time.sleep(0.2)
    # while True:
    #     res = material_track.get_material_track_degree()
    #     if not res:
    #         input("no material near")
    #     # material_track.is_ability_active()
    #     time.sleep(0.2)
