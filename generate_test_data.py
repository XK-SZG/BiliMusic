# -*- coding: utf-8 -*-
"""
快速生成测试数据脚本 - 用于测试播放作息曲线
使用方法：
  python generate_test_data.py           # 生成7天的数据
  python generate_test_data.py 30        # 生成30天的数据
  python generate_test_data.py 1 dense   # 生成1天的密集数据（每5分钟一条）
"""

import sys
import os
from datetime import datetime, timedelta
import random

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database import db, models

def generate_test_data(days=7, mode='normal'):
    """
    生成测试播放记录数据
    
    Args:
        days: 生成多少天的数据
        mode: 'normal' 正常模式，'dense' 密集模式（每5分钟一条）
    """
    print(f"开始生成测试数据 (模式: {mode}, 天数: {days})...")
    
    # 初始化数据库连接
    db_session = next(db.get_db())
    
    try:
        # 检查是否已有视频数据
        video_count = db_session.query(models.Video).count()
        if video_count == 0:
            print("数据库中没有视频数据，先创建一个测试视频...")
            test_video = models.Video(
                bvid="BV1test123456",
                title="测试视频 - 用于数据统计测试",
                owner="测试用户",
                pic="",
                duration=300,
                score=5.0,
                download_status='not_downloaded'
            )
            db_session.add(test_video)
            db_session.commit()
            test_bvid = "BV1test123456"
        else:
            # 使用第一个视频
            test_video = db_session.query(models.Video).first()
            test_bvid = test_video.bvid
            print(f"使用已有视频: {test_video.title} ({test_bvid})")
        
        # 生成播放记录
        now = datetime.now()
        records_added = 0
        
        if mode == 'dense':
            # 密集模式：每5分钟生成一条记录
            print(f"生成过去{days}天的密集播放记录（每5分钟一条）...")
            start_time = now - timedelta(days=days)
            current_time = start_time
            
            while current_time <= now:
                # 随机播放时长（60-300秒）
                play_duration = random.randint(60, 300)
                
                # 创建播放记录
                record = models.PlayRecord(
                    video_bvid=test_bvid,
                    play_duration=play_duration,
                    played_at=current_time
                )
                db_session.add(record)
                records_added += 1
                
                # 更新每日统计
                date_str = current_time.strftime('%Y-%m-%d')
                stat = db_session.query(models.DailyStat).filter(
                    models.DailyStat.date == date_str
                ).first()
                
                if not stat:
                    stat = models.DailyStat(
                        date=date_str,
                        video_play_time=0,
                        app_usage_time=0,
                        network_traffic=0,
                        uncached_traffic=0
                    )
                    db_session.add(stat)
                
                # 确保字段不为 None
                if stat.video_play_time is None:
                    stat.video_play_time = 0
                if stat.app_usage_time is None:
                    stat.app_usage_time = 0
                
                stat.video_play_time += play_duration
                stat.app_usage_time += play_duration + random.randint(10, 60)
                
                # 每100条提交一次，避免内存占用过大
                if records_added % 100 == 0:
                    db_session.commit()
                    print(f"已生成 {records_added} 条记录...")
                
                # 下一个5分钟
                current_time += timedelta(minutes=5)
        
        else:
            # 正常模式：模拟真实的播放习惯
            print(f"生成过去{days}天的播放记录（模拟真实习惯）...")
            
            for day_offset in range(days):
                day_start = now - timedelta(days=day_offset)
                date_str = day_start.strftime('%Y-%m-%d')
                
                # 获取或创建当天的统计记录（每天只查询一次）
                stat = db_session.query(models.DailyStat).filter(
                    models.DailyStat.date == date_str
                ).first()
                
                if not stat:
                    stat = models.DailyStat(
                        date=date_str,
                        video_play_time=0,
                        app_usage_time=0,
                        network_traffic=0,
                        uncached_traffic=0
                    )
                    db_session.add(stat)
                
                # 确保字段不为 None
                if stat.video_play_time is None:
                    stat.video_play_time = 0
                if stat.app_usage_time is None:
                    stat.app_usage_time = 0
                
                # 模拟不同时段的播放习惯
                time_slots = [
                    # (小时, 分钟范围, 播放次数)
                    (7, 60, random.randint(1, 3)),    # 早晨 7:00-8:00
                    (12, 60, random.randint(2, 4)),   # 中午 12:00-13:00
                    (18, 120, random.randint(3, 6)),  # 傍晚 18:00-20:00
                    (21, 120, random.randint(4, 8)),  # 晚上 21:00-23:00
                    (23, 60, random.randint(0, 3)),   # 深夜 23:00-00:00
                ]
                
                for hour, duration_range, count in time_slots:
                    for _ in range(count):
                        # 随机时间点
                        random_minute = random.randint(0, duration_range)
                        try:
                            play_time = day_start.replace(
                                hour=hour,
                                minute=random_minute % 60,
                                second=random.randint(0, 59)
                            )
                        except ValueError:
                            # 处理跨天的情况
                            continue
                        
                        # 随机播放时长（60-600秒）
                        play_duration = random.randint(60, 600)
                        
                        # 创建播放记录
                        record = models.PlayRecord(
                            video_bvid=test_bvid,
                            play_duration=play_duration,
                            played_at=play_time
                        )
                        db_session.add(record)
                        records_added += 1
                        
                        # 累加到当天的统计
                        stat.video_play_time += play_duration
                        stat.app_usage_time += play_duration + random.randint(10, 60)
                
                # 每天提交一次
                if (day_offset + 1) % 10 == 0:
                    db_session.commit()
                    print(f"已生成 {day_offset + 1}/{days} 天的数据...")
        
        # 最终提交
        db_session.commit()
        
        # 统计信息
        total_records = db_session.query(models.PlayRecord).count()
        total_stats = db_session.query(models.DailyStat).count()
        
        print(f"\n✅ 成功生成测试数据！")
        print(f"   新增播放记录: {records_added} 条")
        print(f"   数据库总记录: {total_records} 条")
        print(f"   每日统计记录: {total_stats} 条")
        print(f"   时间范围: {(now - timedelta(days=days-1)).strftime('%Y-%m-%d %H:%M')} 至 {now.strftime('%Y-%m-%d %H:%M')}")
        print(f"\n现在可以刷新数据统计页面查看播放作息曲线了！")
        
    except Exception as e:
        print(f"❌ 生成测试数据失败: {e}")
        db_session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db_session.close()

if __name__ == "__main__":
    # 解析命令行参数
    days = 7
    mode = 'normal'
    
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print("错误：天数必须是整数")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        if sys.argv[2] in ['dense', 'normal']:
            mode = sys.argv[2]
        else:
            print("错误：模式必须是 'normal' 或 'dense'")
            sys.exit(1)
    
    generate_test_data(days, mode)
