# Semantic Scholar S2 API 静态配置

S2_API_KEY = "s2k-0hySn0raZ8rGNZLTjG5Xk1vZdGdZ9UguuPvVJl4Z"

S2_HEADERS = {
    "x-api-key": S2_API_KEY
}

S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"

# 当前 API Key 限制：所有端点累计每秒 1 个请求
S2_RATE_LIMIT_SECONDS = 1.1




client = openreview.api.OpenReviewClient(
    baseurl='https://api2.openreview.net',
    username='l18233195598@stumail.ysu.edu.cn',
    password='Liziyu1213.'
)