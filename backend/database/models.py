from sqlalchemy import (
    Column, String, Integer, Table, ForeignKey, Float, DateTime, Text
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

# 关键修正：在这里直接创建 Base
Base = declarative_base()

# 多对多关联表：收藏夹 <-> 视频
collection_video_assoc = Table(
    'collection_video', Base.metadata,
    Column('collection_id', String, ForeignKey('collections.id', ondelete="CASCADE")),
    Column('video_bvid', String, ForeignKey('videos.bvid', ondelete="CASCADE"))
)

# 多对多关联表：视频 <-> 标签
video_tag_assoc = Table(
    'video_tag', Base.metadata,
    Column('video_bvid', String, ForeignKey('videos.bvid', ondelete="CASCADE")),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete="CASCADE"))
)


class Video(Base):
    __tablename__ = 'videos'
    bvid = Column(String, primary_key=True)
    title = Column(String)
    owner = Column(String, index=True)
    pic = Column(String)
    duration = Column(Integer)
    score = Column(Float, default=5.0)
    local_path = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.now)
    download_status = Column(String, default='not_downloaded', index=True) # not_downloaded, pending, downloading, completed, failed
    download_retry_count = Column(Integer, default=0) # 下载重试次数
    
    # 软裁剪字段
    trim_start = Column(Float, default=0.0)
    trim_end = Column(Float, default=0.0)

    # 来源标识与本地扩展
    is_local = Column(Integer, default=0, index=True) # 0: Bili, 1: Local
    local_mimetype = Column(String, nullable=True) # 记录原始文件类型 (如 audio/mpeg)
    
    # 排序权重
    order_index = Column(Integer, default=0)

    tags = relationship("Tag", secondary=video_tag_assoc, back_populates="videos")
    collections = relationship("Collection", secondary=collection_video_assoc, back_populates="videos")


class Tag(Base):
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, index=True)
    videos = relationship("Video", secondary=video_tag_assoc, back_populates="tags")


class Collection(Base):
    __tablename__ = 'collections'
    id = Column(String, primary_key=True)
    title = Column(String)
    type = Column(String, index=True)  # "bili" or "local"
    order_index = Column(Integer, default=0)
    videos = relationship("Video", secondary=collection_video_assoc, back_populates="collections")

class Theme(Base):
    __tablename__ = 'themes'
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    is_default = Column(Integer, default=0) # 0: False, 1: True
    settings = Column(Text, nullable=False) # JSON
    backgrounds = Column(Text, nullable=True) # JSON

class PlayRecord(Base):
    __tablename__ = 'play_records'
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_bvid = Column(String, ForeignKey('videos.bvid', ondelete="CASCADE"), index=True)
    played_at = Column(DateTime, default=datetime.now, index=True)
    play_duration = Column(Integer, default=0) # 播放时长(秒)
    
    video = relationship("Video")

class DailyStat(Base):
    __tablename__ = 'daily_stats'
    date = Column(String, primary_key=True) # YYYY-MM-DD
    app_usage_time = Column(Integer, default=0) # 软件使用时长(秒)
    video_play_time = Column(Integer, default=0) # 视频播放总时长(秒)
    network_traffic = Column(Integer, default=0) # 网络流量消耗(字节)
    uncached_traffic = Column(Integer, default=0) # 未缓存视频流量消耗(字节)
