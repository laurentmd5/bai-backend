import inspect
from app.services.cache.redis_cache import RedisCacheService
print('sadd', inspect.signature(RedisCacheService.sadd))
print('sismember', inspect.signature(RedisCacheService.sismember))
print('srem', inspect.signature(RedisCacheService.srem))
print('smembers', inspect.signature(RedisCacheService.smembers))
