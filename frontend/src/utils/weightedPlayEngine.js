/**
 * [性能优化] 权重播放引擎 - 使用前缀和 + 二分查找实现 O(log N) 复杂度
 * 
 * 原始算法问题：
 * - 每次切歌都要遍历整个队列计算权重（O(N)）
 * - 在万级播放列表中会导致明显卡顿
 * 
 * 优化策略：
 * - 预计算：在队列变化或评分更新时一次性计算前缀和数组
 * - 查询：使用二分查找在 O(log N) 时间内定位目标
 */

export class WeightedPlayEngine {
  constructor() {
    this.prefixSums = []
    this.totalWeight = 0
    this.validIndices = []
    this.isBuilt = false
  }

  /**
   * [预计算阶段] 构建前缀和数组 - O(N) 复杂度
   * @param {Array} queue - 播放队列
   * @param {Array} recentHistory - 最近播放历史索引
   * @param {String} mode - 权重模式 ('positive' | 'negative')
   * @param {Number} sensitivity - 权重敏感度 (默认 2.0)
   */
  build(queue, recentHistory = [], mode = 'positive', sensitivity = 2.0) {
    this.prefixSums = []
    this.validIndices = []
    this.totalWeight = 0

    const historySet = new Set(recentHistory)
    const penaltyFactor = 0.1 // 历史中的视频权重降低到 10%

    for (let i = 0; i < queue.length; i++) {
      const video = queue[i]
      const score = video.score ?? 5.0

      // 计算基础权重
      let baseWeight = mode === 'positive' ? score : (11 - score)
      let weight = Math.pow(baseWeight / 5, sensitivity)

      // 对历史中的视频应用惩罚
      if (historySet.has(i)) {
        weight *= penaltyFactor
      }

      // 累加权重并记录前缀和
      this.totalWeight += weight
      this.prefixSums.push(this.totalWeight)
      this.validIndices.push(i)
    }

    this.isBuilt = true

  }

  /**
   * [查询阶段] 加权随机选择下一首 - O(log N) 复杂度
   * @returns {Number} 选中的队列索引，-1 表示失败
   */
  next() {
    if (!this.isBuilt || this.validIndices.length === 0) {
      console.warn('[权重引擎] 未构建或队列为空')
      return -1
    }

    if (this.totalWeight === 0) {
      console.warn('[权重引擎] 总权重为 0，回退到随机选择')
      return this.validIndices[Math.floor(Math.random() * this.validIndices.length)]
    }

    // 生成随机权重值
    const randomWeight = Math.random() * this.totalWeight

    // 二分查找：找到第一个 prefixSum >= randomWeight 的位置
    let left = 0
    let right = this.prefixSums.length - 1
    let targetIndex = right

    while (left <= right) {
      const mid = Math.floor((left + right) / 2)
      if (this.prefixSums[mid] >= randomWeight) {
        targetIndex = mid
        right = mid - 1
      } else {
        left = mid + 1
      }
    }

    return this.validIndices[targetIndex]
  }

  /**
   * 检查引擎是否已构建
   */
  isReady() {
    return this.isBuilt && this.validIndices.length > 0
  }

  /**
   * 重置引擎状态
   */
  reset() {
    this.prefixSums = []
    this.totalWeight = 0
    this.validIndices = []
    this.isBuilt = false
  }

  /**
   * 获取权重分布统计（用于调试）
   */
  getWeightDistribution(queue) {
    if (!this.isReady()) return []

    return this.validIndices.map((idx, i) => {
      const video = queue[idx]
      const weight = i === 0 ? this.prefixSums[0] : this.prefixSums[i] - this.prefixSums[i - 1]
      const probability = (weight / this.totalWeight * 100).toFixed(2)

      return {
        index: idx,
        title: video.title,
        score: video.score,
        weight: weight.toFixed(4),
        probability: `${probability}%`
      }
    })
  }
}
