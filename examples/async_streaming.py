"""Пример асинхронного захвата кадров с помощью AsyncKinectSensor."""

import asyncio

from kinect_next import StreamType
from kinect_next.aio import AsyncKinectSensor


async def main():
    print("Запуск асинхронного стрима (AsyncKinectSensor)...")
    
    async with AsyncKinectSensor(streams=StreamType.DEPTH | StreamType.BODY) as kinect:
        count = 0
        async for frameset in kinect.stream():
            count += 1
            tracked = len(frameset.tracked_bodies)
            
            # Демонстрация неблокирующего asyncio
            if frameset.depth:
                center_dist = frameset.depth.distance_at(256, 212)
                print(f"[Async Frame #{count:03d}] Дистанция по центру: {center_dist:.2f} м | Людей: {tracked}")

            # Имитация параллельной асинхронной задачи (например, отправка в WebSocket)
            await asyncio.sleep(0.01)

            if count >= 20:
                print("Асинхронный тест успешно завершен.")
                break


if __name__ == "__main__":
    asyncio.run(main())