import asyncio
from database import engine, Base
import models  # 모델들을 불러와서 Base에 등록

async def init_db():
    print("Creating tables...")
    # 비동기 엔진을 사용하여 스키마 생성
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    print("Tables created successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())