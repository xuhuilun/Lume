import base64
import io
from datetime import UTC, datetime

from PIL import Image, ImageDraw, ImageFont

from .schemas import ImageInput, MessageInput


def sample_messages():
    image = Image.new("RGB", (720, 320), "#f5f3ed")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=30)
    for y, line in enumerate(
        [
            "SYNTHETIC TEST FIXTURE",
            "connection pool",
            "pool_size = 20",
            "status = healthy",
            "Not a production screenshot",
        ]
    ):
        draw.text((30, 20 + y * 55), line, fill="#163c32", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    at = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
    return [
        MessageInput(
            source_id="demo-1",
            text="合成资料：服务v1.8出现E_CONN_42，连接池等待超时。",
            sent_at=at,
            author="演示·研发",
        ),
        MessageInput(
            source_id="demo-2",
            text="排查发现pool_size=5，建议调整为20；需要复测确认。",
            sent_at=at,
            author="演示·支持",
            reply_to="demo-1",
        ),
        MessageInput(
            source_id="demo-3",
            text="已将pool_size调整为20，复测连接恢复；适用环境为v1.8。",
            sent_at=at,
            author="演示·研发",
            reply_to="demo-2",
        ),
        MessageInput(
            source_id="demo-4",
            text="连接池参数示意图。此图为人工构造测试资料。",
            sent_at=at,
            author="演示·维护",
            reply_to="demo-3",
            images=[
                ImageInput(
                    filename="synthetic-config.png",
                    base64=base64.b64encode(output.getvalue()).decode(),
                )
            ],
        ),
    ]
