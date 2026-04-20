import request from './request'

export default {
  // 记录播放记录
  recordPlay(video_bvid, play_duration) {
    return request.post('/stats/play_record', { video_bvid, play_duration })
  },

  // 记录软件使用时长
  recordAppUsage(duration) {
    return request.post('/stats/app_usage', { duration })
  },

  // 记录网络流量
  recordNetworkTraffic(traffic, is_cached) {
    return request.post('/stats/network_traffic', { traffic, is_cached })
  },

  // 获取统计概览
  getOverview() {
    return request.get('/stats/overview')
  },

  // 获取播放作息曲线
  getPlaySchedule() {
    return request.get('/stats/play_schedule')
  },

  // 获取排行榜
  getRankings() {
    return request.get('/stats/rankings')
  },

  // 获取播放作息曲线智能分析
  getPlayScheduleAnalysis() {
    return request.get('/stats/play_schedule_analysis')
  }
}
