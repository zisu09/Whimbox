from whimbox.common.utils.utils import *
from whimbox.common.utils.img_utils import *
from whimbox.common.utils.posi_utils import *
from whimbox.common.logger import logger
from whimbox.map.detection.cvars import *
from whimbox.map.detection.map_assets import *
from whimbox.map.detection.utils import *
import typing as t


class BigMap:

    def __init__(self):
        # Usually to be 0.4~0.5
        self.bigmap_similarity = 0.
        # Usually > 0.05
        self.bigmap_similarity_local = 0.
        # Current position on png
        self.bigmap_position: t.Tuple[float, float] = (0, 0)


    def _predict_bigmap(self, image):
        """
        Args:
            image:

        Returns: (new)png position
        """
        scale = BIGMAP_POSITION_SCALE_DICT[self.map_name] * BIGMAP_SEARCH_SCALE
        image = rgb2luma(image)
        center = np.array(image_size(image)) / 2 * scale
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)

        result = cv2.matchTemplate(MAP_ASSETS_DICT[self.map_name]["luma_0125x"].img, image, cv2.TM_CCOEFF_NORMED)
        _, sim, _, loca = cv2.minMaxLoc(result)

        # Gaussian filter to get local maximum
        local_maximum = cv2.subtract(result, cv2.GaussianBlur(result, (9, 9), 0))
        mask = image_center_crop(MAP_ASSETS_DICT[self.map_name]["mask_0125x"].img, size=image_size(local_maximum))
        local_maximum = cv2.copyTo(local_maximum, mask)
        _, local_sim, _, loca = cv2.minMaxLoc(local_maximum)

        # Calculate the precise location using CUBIC
        area = area_offset((-4, -4, 4, 4), offset=loca)
        area = AnchorPosi(area[0], area[1], area[2], area[3])
        precise = crop(result, area)
        precise_sim, precise_loca = cubic_find_maximum(precise, precision=0.05)
        precise_loca -= 5

        global_loca = (loca + precise_loca + center) / BIGMAP_SEARCH_SCALE
        self.bigmap_similarity = sim
        self.bigmap_similarity_local = local_sim
        self.bigmap_position = global_loca

        if CV_DEBUG_MODE:
            cv2.imshow("image",image)
            loca = loca + precise_loca + center
            area = AnchorPosi(loca[0]-200, loca[1]-200, loca[0]+200, loca[1]+200)
            area = AnchorPosi(area.x1, area.y1, area.x2, area.y2)
            close_area = crop(MAP_ASSETS_DICT[self.map_name]["luma_0125x"].img, area)
            center = (close_area.shape[1] // 2, close_area.shape[0] // 2)
            cv2.circle(close_area, center, 5, (0, 0, 255), 2)
            cv2.imshow("bigmap_nearby", close_area)
            cv2.waitKey(1)


        return sim, global_loca

    def update_bigmap(self, image):
        """
        Get position on bigmap (where you enter from the M button)

        The following attributes will be set:
        - bigmap_similarity
        - bigmap_similarity_local
        - bigmap
        """
        self._predict_bigmap(image)

        logger.trace(
            f'BigMap '
            f'P:({float2str(self.bigmap_position[0], 4)}, {float2str(self.bigmap_position[1], 4)}) '
            f'({float2str(self.bigmap_similarity, 3)}|{float2str(self.bigmap_similarity_local, 3)})'
        )

if __name__ == '__main__':
    CV_DEBUG_MODE = True
    bm = BigMap()
    bm.map_name = MAP_NAME_STARSEA
    from whimbox.interaction.interaction_core import itt
    import time

    while 1:
        bm.update_bigmap(itt.capture())
        print(bm.bigmap_position)
        time.sleep(0.1)
