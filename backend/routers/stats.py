# -*- coding: utf-8 -*-
# Path: backend/routers/stats.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Dict
import logging
import random

from ..database import db, models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])

class PlayRecordReq(BaseModel):
    video_bvid: str
    play_duration: int  # 秒

class AppUsageReq(BaseModel):
    duration: int  # 秒

class NetworkTrafficReq(BaseModel):
    traffic: int  # 字节
    is_cached: bool

@router.post("/play_record")
def record_play(req: PlayRecordReq, db_session: Session = Depends(db.get_db)):
    """记录视频播放记录"""
    try:
        record = models.PlayRecord(
            video_bvid=req.video_bvid,
            play_duration=req.play_duration,
            played_at=datetime.now()
        )
        db_session.add(record)
        
        # 更新当日统计
        today = datetime.now().strftime('%Y-%m-%d')
        stat = db_session.query(models.DailyStat).filter(models.DailyStat.date == today).first()
        if not stat:
            stat = models.DailyStat(date=today)
            db_session.add(stat)
        
        if stat.video_play_time is None:
            stat.video_play_time = 0
        stat.video_play_time += req.play_duration
        
        db_session.commit()
        return {"code": 0, "message": "记录成功"}
    except Exception as e:
        logger.error(f"记录播放失败: {e}")
        db_session.rollback()
        return {"code": -1, "message": str(e)}

@router.post("/app_usage")
def record_app_usage(req: AppUsageReq, db_session: Session = Depends(db.get_db)):
    """记录软件使用时长"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        stat = db_session.query(models.DailyStat).filter(models.DailyStat.date == today).first()
        if not stat:
            stat = models.DailyStat(date=today)
            db_session.add(stat)
        
        if stat.app_usage_time is None:
            stat.app_usage_time = 0
        stat.app_usage_time += req.duration
        db_session.commit()
        return {"code": 0, "message": "记录成功"}
    except Exception as e:
        logger.error(f"记录使用时长失败: {e}")
        db_session.rollback()
        return {"code": -1, "message": str(e)}

@router.post("/network_traffic")
def record_network_traffic(req: NetworkTrafficReq, db_session: Session = Depends(db.get_db)):
    """记录网络流量消耗"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        stat = db_session.query(models.DailyStat).filter(models.DailyStat.date == today).first()
        if not stat:
            stat = models.DailyStat(date=today)
            db_session.add(stat)
        
        if stat.network_traffic is None:
            stat.network_traffic = 0
        stat.network_traffic += req.traffic
        
        if not req.is_cached:
            if stat.uncached_traffic is None:
                stat.uncached_traffic = 0
            stat.uncached_traffic += req.traffic
        db_session.commit()
        return {"code": 0, "message": "记录成功"}
    except Exception as e:
        logger.error(f"记录流量失败: {e}")
        db_session.rollback()
        return {"code": -1, "message": str(e)}

@router.get("/overview")
def get_stats_overview(db_session: Session = Depends(db.get_db)):
    """获取统计概览数据"""
    try:
        # 视频数据统计
        total_videos = db_session.query(func.count(models.Video.bvid)).scalar() or 0
        cached_videos = db_session.query(func.count(models.Video.bvid)).filter(
            models.Video.download_status == 'completed'
        ).scalar() or 0
        uncached_videos = total_videos - cached_videos
        
        # 播放记录统计
        total_plays = db_session.query(func.count(models.PlayRecord.id)).scalar() or 0
        
        # 缓存视频播放次数和时长
        cached_result = db_session.query(
            func.count(models.PlayRecord.id),
            func.sum(models.PlayRecord.play_duration)
        ).join(
            models.Video, models.PlayRecord.video_bvid == models.Video.bvid
        ).filter(models.Video.download_status == 'completed').first()
        
        cached_plays = cached_result[0] or 0
        cached_play_time = cached_result[1] or 0
        
        # 未缓存视频播放次数
        uncached_plays = total_plays - cached_plays
        
        # 时长统计（所有历史记录）
        total_app_usage = db_session.query(func.sum(models.DailyStat.app_usage_time)).scalar() or 0
        total_video_play_time = db_session.query(func.sum(models.DailyStat.video_play_time)).scalar() or 0
        
        # 未缓存视频播放时长
        uncached_play_time = total_video_play_time - cached_play_time
        
        # 流量统计
        total_traffic = db_session.query(func.sum(models.DailyStat.network_traffic)).scalar() or 0
        total_uncached_traffic = db_session.query(func.sum(models.DailyStat.uncached_traffic)).scalar() or 0
        
        return {
            "code": 0,
            "data": {
                "total_videos": total_videos,
                "cached_videos": cached_videos,
                "uncached_videos": uncached_videos,
                "total_plays": total_plays,
                "cached_plays": cached_plays,
                "uncached_plays": uncached_plays,
                "total_app_usage": total_app_usage,
                "total_video_play_time": total_video_play_time,
                "cached_play_time": cached_play_time,
                "uncached_play_time": uncached_play_time,
                "total_traffic": total_traffic,
                "total_uncached_traffic": total_uncached_traffic
            }
        }
    except Exception as e:
        logger.error(f"获取统计概览失败: {e}")
        return {"code": -1, "message": str(e)}

@router.get("/play_schedule")
def get_play_schedule(db_session: Session = Depends(db.get_db)):
    """获取播放作息曲线数据（1年内数据，5分钟步长聚合）"""
    try:
        now = datetime.now()
        start_time = now - timedelta(days=365) # 1 year
        
        records = db_session.query(models.PlayRecord).filter(
            models.PlayRecord.played_at >= start_time
        ).all()
        
        buckets = {}
        for record in records:
            # 获取毫秒级时间戳，按5分钟(300,000ms)对齐
            ts = int(record.played_at.timestamp() * 1000)
            bucket_ts = ts - (ts % 300000)
            buckets[bucket_ts] = buckets.get(bucket_ts, 0) + record.play_duration
            
        # 返回非空的桶数据：[ [timestamp, duration], ... ]
        data = [[k, v] for k, v in sorted(buckets.items())]
        
        return {
            "code": 0,
            "data": data
        }
    except Exception as e:
        logger.error(f"获取播放作息曲线失败: {e}")
        return {"code": -1, "message": str(e)}

@router.get("/play_schedule_analysis")
def get_play_schedule_analysis(db_session: Session = Depends(db.get_db)):
    """获取播放作息曲线智能分析（优化版：使用数据库聚合，避免内存溢出）"""
    try:
        from sqlalchemy import case, Integer
        
        # 优化：检查是否有记录（只查询计数，不加载数据）
        total_count = db_session.query(func.count(models.PlayRecord.id)).scalar()
        if total_count == 0:
            return {"code": 0, "data": {"message": "播放列表空空如也，快去唤醒你的耳朵吧！", "icon": "🎵", "persona": "萌新听众"}}
        
        # 优化：使用数据库聚合函数直接计算，避免加载所有记录到内存
        # 提取小时字段（SQLite 使用 strftime）
        hour_expr = func.cast(func.strftime('%H', models.PlayRecord.played_at), Integer)
        
        # 使用 CASE WHEN 进行时段分类并聚合
        result = db_session.query(
            # 凌晨 0-6
            func.sum(
                case(
                    (hour_expr < 6, models.PlayRecord.play_duration),
                    else_=0
                )
            ).label('dawn'),
            # 早晨 6-10
            func.sum(
                case(
                    ((hour_expr >= 6) & (hour_expr < 10), models.PlayRecord.play_duration),
                    else_=0
                )
            ).label('morning'),
            # 中午 10-14
            func.sum(
                case(
                    ((hour_expr >= 10) & (hour_expr < 14), models.PlayRecord.play_duration),
                    else_=0
                )
            ).label('noon'),
            # 下午 14-18
            func.sum(
                case(
                    ((hour_expr >= 14) & (hour_expr < 18), models.PlayRecord.play_duration),
                    else_=0
                )
            ).label('afternoon'),
            # 傍晚 18-22
            func.sum(
                case(
                    ((hour_expr >= 18) & (hour_expr < 22), models.PlayRecord.play_duration),
                    else_=0
                )
            ).label('evening'),
            # 深夜 22-24
            func.sum(
                case(
                    (hour_expr >= 22, models.PlayRecord.play_duration),
                    else_=0
                )
            ).label('night')
        ).first()
        
        # 获取聚合结果
        time_stats = {
            "dawn": result.dawn or 0,      # 00:00 - 05:59 (凌晨/修仙)
            "morning": result.morning or 0,   # 06:00 - 09:59 (早晨/通勤)
            "noon": result.noon or 0,      # 10:00 - 13:59 (中午/午休)
            "afternoon": result.afternoon or 0, # 14:00 - 17:59 (下午/摸鱼)
            "evening": result.evening or 0,   # 18:00 - 21:59 (傍晚/放松)
            "night": result.night or 0      # 22:00 - 23:59 (深夜/网抑)
        }
                
        total_time = sum(time_stats.values())
        if total_time == 0:
            return {"code": 0, "data": {"message": "暂无有效播放数据", "icon": "📊", "persona": "神秘潜水员"}}
            
        # 2. 计算各时段占比
        ratios = {k: v / total_time for k, v in time_stats.items()}
        
        # 找出占比最高的一个或两个时段
        sorted_ratios = sorted(ratios.items(), key=lambda x: x[1], reverse=True)
        top1_period, top1_ratio = sorted_ratios[0]
        top2_period, top2_ratio = sorted_ratios[1]

        # 3. 智能画像与文案分析引擎
        message = ""
        icon = ""
        persona = ""

        # --- 场景 A: 极端/重度偏好 (单一时段 > 75%) ---
        if top1_ratio > 0.75:
            extreme_pool = {
                "dawn": {"persona": "修仙狂魔", "icon": "🦉", "msgs":["宇宙都睡了，只有你的耳机还醒着。", "熬最晚的夜，听最嗨的歌，但发际线警告哦！"]},
                "night": {"persona": "深夜守门员", "icon": "🌙", "msgs":["夜幕降临，你的精神世界才刚刚苏醒。", "是emo了，还是在享受独处的静谧？"]},
                "morning": {"persona": "晨曦鸟", "icon": "🌅", "msgs":["这么早就全功率运转？自律得让人害怕！", "第一缕阳光和第一首歌，你都没错过。"]},
                "noon": {"persona": "干饭BGM", "icon": "🍱", "msgs":["别人午休你听歌，音乐是你真正的精神食粮。", "午间充能完毕，下午继续发光发热！"]},
                "afternoon": {"persona": "午后慵懒家", "icon": "☕", "msgs":["阳光正好，不如配着这首歌喝杯下午茶？", "下午的困意，全靠耳机里的节奏在续命。"]},
                "evening": {"persona": "夕阳漫步者", "icon": "🌆", "msgs":["卸下一天的疲惫，把时间还给自己和音乐。", "夜色温柔，最适合在这个时间让思绪放飞。"]}
            }
            conf = extreme_pool[top1_period]
            persona, icon, message = conf["persona"], conf["icon"], random.choice(conf["msgs"])

        # --- 场景 B: 组合行为画像 (识别特定生活规律) ---
        # 1. 通勤模式：早晨 + 傍晚 占比极高
        elif ratios["morning"] + ratios["evening"] > 0.65 and top1_ratio < 0.5:
            persona, icon = "披星戴月通勤族", "🚌"
            message = random.choice([
                "早出晚归，音乐是你路上最好的陪伴。", 
                "车水马龙中，戴上耳机就是你自己的小宇宙。"
            ])
            
        # 2. 白天打工人模式：早+中+下午 占比极高，晚上基本不听
        elif ratios["morning"] + ratios["noon"] + ratios["afternoon"] > 0.8:
            persona, icon = "全天候打工人", "💻"
            message = random.choice([
                "没有音乐做白噪音，根本无法开启工作/学习模式对吧？",
                "高效运转的一天！连代码/作业里都带着BGM的节奏。"
            ])

        # 3. 夜猫子模式：傍晚 + 深夜 + 凌晨 > 0.7
        elif ratios["evening"] + ratios["night"] + ratios["dawn"] > 0.7:
            persona, icon = "越夜越美丽", "✨"
            message = random.choice([
                "白天属于世界，夜晚的音乐才属于自己。",
                "夜间出没注意！你的听觉神经在晚上格外敏锐。"
            ])

        # --- 场景 C: 普通偏好 (单一时段 40% ~ 75%) ---
        elif top1_ratio >= 0.4:
            normal_pool = {
                "dawn": {"persona": "凌晨微光", "icon": "🌌", "msgs": ["偶尔修仙，音乐是你深夜的慰藉。"]},
                "morning": {"persona": "元气早晨", "icon": "☀️", "msgs":["元气满满的一天从音乐开始~"]},
                "noon": {"persona": "午间小憩", "icon": "🎧", "msgs": ["午休时间，来点音乐放松一下紧绷的神经。"]},
                "afternoon": {"persona": "下午茶DJ", "icon": "🍰", "msgs": ["享受午后时光，音乐和阳光更配哦。"]},
                "evening": {"persona": "黄昏听众", "icon": "🌇", "msgs":["傍晚时分，用一首歌告别今天的喧嚣。"]},
                "night": {"persona": "星空聆听者", "icon": "🌠", "msgs": ["夜色渐浓，适合听点舒缓的旋律入眠。"]}
            }
            conf = normal_pool[top1_period]
            persona, icon, message = conf["persona"], conf["icon"], random.choice(conf["msgs"])

        # --- 场景 D: 绝对均衡 (没有任何时段超过 30%) ---
        elif top1_ratio < 0.3:
            persona, icon = "全能六边形战士", "☯️"
            message = random.choice([
                "随时随地，想听就听！你的音乐作息无懈可击。",
                "随性派听众认证！无论什么时间，只要有感觉就会按下播放键。"
            ])

        # --- 场景 E: 兜底 (30% ~ 40%之间，相对均衡但有小偏好) ---
        else:
            persona, icon = "随性音乐家", "🎶"
            message = "音乐陪伴着你生活的各个角落，保持这副好心情吧！"

        return {
            "code": 0,
            "data": {
                "persona": persona,    # 新增：用户人设标签
                "message": message,
                "icon": icon,
                "statistics": {
                    "dawn": round(ratios["dawn"] * 100, 1),
                    "morning": round(ratios["morning"] * 100, 1),
                    "noon": round(ratios["noon"] * 100, 1),
                    "afternoon": round(ratios["afternoon"] * 100, 1),
                    "evening": round(ratios["evening"] * 100, 1),
                    "night": round(ratios["night"] * 100, 1)
                }
            }
        }
    except Exception as e:
        # logger.error(f"获取播放作息分析失败: {e}")
        return {"code": -1, "message": str(e)}

@router.get("/rankings")
def get_rankings(db_session: Session = Depends(db.get_db)):
    """获取视频排行榜"""
    try:
        # 播放次数排行
        play_count_ranking = db_session.query(
            models.PlayRecord.video_bvid,
            func.count(models.PlayRecord.id).label('play_count')
        ).group_by(models.PlayRecord.video_bvid).order_by(desc('play_count')).limit(10).all()
        
        # 播放时长排行
        play_duration_ranking = db_session.query(
            models.PlayRecord.video_bvid,
            func.sum(models.PlayRecord.play_duration).label('total_duration')
        ).group_by(models.PlayRecord.video_bvid).order_by(desc('total_duration')).limit(10).all()
        
        # 评分排行
        score_ranking = db_session.query(models.Video).order_by(desc(models.Video.score)).limit(10).all()
        
        # 获取视频详细信息
        def get_video_info(bvid):
            video = db_session.query(models.Video).filter(models.Video.bvid == bvid).first()
            if video:
                pic_url = video.pic
                if pic_url and not pic_url.startswith('http') and not pic_url.startswith('/'):
                    pic_url = f"/local_covers/{pic_url}"
                return {
                    "bvid": video.bvid,
                    "title": video.title,
                    "owner": video.owner,
                    "pic": pic_url
                }
            return None
        
        play_count_list = []
        for bvid, count in play_count_ranking:
            info = get_video_info(bvid)
            if info:
                info['play_count'] = count
                play_count_list.append(info)
        
        play_duration_list = []
        for bvid, duration in play_duration_ranking:
            info = get_video_info(bvid)
            if info:
                info['total_duration'] = duration
                play_duration_list.append(info)
        
        score_list = []
        for video in score_ranking:
            pic_url = video.pic
            if pic_url and not pic_url.startswith('http') and not pic_url.startswith('/'):
                pic_url = f"/local_covers/{pic_url}"
            score_list.append({
                "bvid": video.bvid,
                "title": video.title,
                "owner": video.owner,
                "pic": pic_url,
                "score": video.score
            })
        
        return {
            "code": 0,
            "data": {
                "play_count": play_count_list,
                "play_duration": play_duration_list,
                "score": score_list
            }
        }
    except Exception as e:
        logger.error(f"获取排行榜失败: {e}")
        return {"code": -1, "message": str(e)}
