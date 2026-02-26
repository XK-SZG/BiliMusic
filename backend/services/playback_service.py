import random
from typing import List
from ..database.models import Video


class PlaybackManager:
    def __init__(self):
        self.playlist: List[Video] = []
        self.current_index: int = -1
        self.mode: str = "sequential"  # sequential, random, weighted_random

    def load_playlist(self, videos: List[Video]):
        """加载新的播放列表并重置状态"""
        self.playlist = videos
        self.current_index = 0 if self.playlist else -1
        if self.mode == "random":
            random.shuffle(self.playlist)

    def set_mode(self, new_mode: str):
        if new_mode in ["sequential", "random", "weighted_random"]:
            self.mode = new_mode
            # 如果切换到随机模式，立即洗牌
            if new_mode == "random":
                random.shuffle(self.playlist)

    def _get_weighted_random_video(self) -> Video:
        """根据视频分数（权重）计算并返回下一首视频"""
        if not self.playlist:
            return None

        total_weight = sum(v.score for v in self.playlist)
        if total_weight <= 0:  # 避免所有分数为0的情况
            return random.choice(self.playlist)

        r = random.uniform(0, total_weight)
        upto = 0
        for video in self.playlist:
            if upto + video.score >= r:
                return video
            upto += video.score
        return self.playlist[-1]  # 兜底

    def next_video(self) -> Video:
        if not self.playlist:
            return None

        if self.mode == "weighted_random":
            video = self._get_weighted_random_video()
            # 更新 index 以便 get_current_state 能正确显示
            if video in self.playlist:
                self.current_index = self.playlist.index(video)
            return video

        if self.mode == "random":
            self.current_index = (self.current_index + 1) % len(self.playlist)
        else:  # sequential
            self.current_index = (self.current_index + 1) % len(self.playlist)

        return self.playlist[self.current_index]

    def previous_video(self) -> Video:
        if not self.playlist:
            return None
        # 为简单起见，上一首不支持权重随机，直接返回列表中的上一首
        self.current_index = (self.current_index - 1 + len(self.playlist)) % len(self.playlist)
        return self.playlist[self.current_index]

    def get_current_state(self):
        if 0 <= self.current_index < len(self.playlist):
            return {
                "video": self.playlist[self.current_index],
                "index": self.current_index,
                "playlist_length": len(self.playlist),
                "mode": self.mode
            }
        return None