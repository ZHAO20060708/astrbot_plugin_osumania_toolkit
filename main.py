import random
import time
import asyncio
import aiohttp
from io import BytesIO
from pathlib import Path
from PIL import Image as PILImage, ImageChops, ImageFilter

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Image, Record, Reply

@register("osumania_toolkit", "ZHAO20060708", "A plugin for osu!mania tools like greek letter overlay", "1.0.0", "")
class OsuManiaToolkit(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.plugin_dir = Path(__file__).parent
        self.image_dir = self.plugin_dir / "images"
        self.image_dir.mkdir(exist_ok=True)
        self.cache_dir = self.plugin_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)

    def add_chromatic_aberration(self, image: PILImage.Image, intensity: int = 4) -> PILImage.Image:
        intensity = max(1, min(20, intensity))
        r, g, b = image.split()[:3]
        
        r_offset = ImageChops.offset(r, -intensity, -intensity)
        g_offset = ImageChops.offset(g, 0, 0)
        b_offset = ImageChops.offset(b, intensity, intensity)
        
        if len(image.split()) == 4:
            a = image.split()[3]
            return PILImage.merge("RGBA", (r_offset, g_offset, b_offset, a))
        else:
            return PILImage.merge("RGB", (r_offset, g_offset, b_offset))

    def add_glitch_effect(self, image: PILImage.Image, intensity: int = 0) -> PILImage.Image:
        intensity = max(0, min(5, intensity))
        if intensity == 0:
            return image.copy()
        
        width, height = image.size
        glitched = image.copy()
        
        if intensity >= 1:
            num_shifts = min(3, max(1, intensity))
            for _ in range(num_shifts):
                max_shift = max(5, int(width * 0.1 * intensity / 5))
                shift_amount = random.randint(2, max_shift)
                shift_direction = random.choice([-1, 1])
                
                min_shift_height = height // 20
                max_shift_height = height // 6 + (height // 12) * (intensity - 1)
                shift_height = random.randint(min_shift_height, max_shift_height)
                shift_y = random.randint(0, height - shift_height)
                
                region = glitched.crop((0, shift_y, width, shift_y + shift_height))
                glitched.paste(region, (shift_amount * shift_direction, shift_y))
            
        if intensity >= 2:
            base_noise = 50
            noise_intensity = base_noise * (intensity ** 2)
            for _ in range(noise_intensity):
                x = random.randint(0, width - 1)
                y = random.randint(0, height - 1)
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 255)
                glitched.putpixel((x, y), color)
            
            if intensity >= 3:
                num_blocks = random.randint(1, intensity - 1)
                for _ in range(num_blocks):
                    block_width = random.randint(5, 20)
                    block_height = random.randint(5, 20)
                    block_x = random.randint(0, width - block_width)
                    block_y = random.randint(0, height - block_height)
                    
                    for bx in range(block_width):
                        for by in range(block_height):
                            if random.random() < 0.7:
                                px = min(block_x + bx, width - 1)
                                py = min(block_y + by, height - 1)
                                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255), 255)
                                glitched.putpixel((px, py), color)
        
        if intensity >= 3:
            scanline_spacing = random.randint(8 - intensity, 15 - intensity)
            scanline_probability = 0.15 + (intensity - 3) * 0.05
            
            for y in range(0, height, scanline_spacing):
                if random.random() < scanline_probability:
                    line_height = random.randint(1, 2)
                    line_region = glitched.crop((0, y, width, y + line_height))
                    brightness = 150 + (intensity - 3) * 25
                    line_region = ImageChops.multiply(line_region, PILImage.new("RGBA", (width, line_height), (brightness, brightness, brightness, 255)))
                    glitched.paste(line_region, (0, y))
                    
        if intensity >= 4:
            blur_radius = 0.5 + (intensity - 4) * 0.5
            glitched = glitched.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            if intensity >= 5:
                if len(glitched.split()) >= 3:
                    r, g, b = glitched.split()[:3]
                    offset_x = random.randint(-3, 3)
                    offset_y = random.randint(-3, 3)
                    
                    r_offset = ImageChops.offset(r, offset_x, offset_y)
                    b_offset = ImageChops.offset(b, -offset_x, -offset_y)
                    
                    if len(glitched.split()) == 4:
                        a = glitched.split()[3]
                        glitched = PILImage.merge("RGBA", (r_offset, g, b_offset, a))
                    else:
                        glitched = PILImage.merge("RGB", (r_offset, g, b_offset))
        
        return glitched

    def resize_greek_image(self, greek_img: PILImage.Image, original_width: int, original_height: int) -> PILImage.Image:
        greek_w, greek_h = greek_img.size
        min_original_dimension = min(original_width, original_height)
        target_size = int(min_original_dimension * 1.8)
        scale_ratio = target_size / max(greek_w, greek_h)
        new_width = int(greek_w * scale_ratio)
        new_height = int(greek_h * scale_ratio)
        if new_width < 200:
            new_width = 200
            new_height = int(greek_h * (200 / greek_w))
        return greek_img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

    @filter.command("osugreek")
    async def osugreek_cmd(self, event: AstrMessageEvent, greek_name: str = "", chromatic_intensity: int = 4, glitch_intensity: int = 0):
        '''生成希腊字母特效图片
        用法: /osugreek <希腊字母名称> [色散强度] [故障强度]
        说明: 支持在命令中附带图片或回复一张图片。
        参数说明:
        - 希腊字母名称: 内置的希腊字母名称（可通过/osugreek help查看）
        - 色散强度: 将图片RGB分离。范围[1,20], 不填则默认4。
        - 故障强度: 将图片应用故障效果。范围[0,5], 不填则默认0。
        '''
        if not greek_name or greek_name == "help":
            help_text = "用法：/osugreek <希腊字母名称> [色散强度] [故障强度]\n说明: 支持在命令中附带图片或回复一张图片。\n参数说明: \n- 色散强度: 将图片RGB分离。范围[1,20], 不填则默认4。\n- 故障强度: 将图片应用故障效果。强度决定故障效果的程度。范围[0,5], 不填则默认0。"
            available = [f.stem for f in self.image_dir.glob("*.png")]
            available.sort()
            help_text += f"\n可用的希腊字母名称有: {', '.join(available)}"
            yield event.plain_result(help_text)
            return

        image_url = None
        
        components_to_check = list(event.message_obj.message)
        for comp in components_to_check:
            if isinstance(comp, Reply) and comp.chain:
                components_to_check.extend(comp.chain)

        for component in components_to_check:
            if isinstance(component, Image):
                if hasattr(component, "url") and component.url:
                    image_url = component.url
                elif hasattr(component, "file") and component.file and component.file.startswith("http"):
                    image_url = component.file
                break

        if not image_url:
            yield event.plain_result("请在命令中附带一张图片，或回复包含图片的被引用消息")
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        yield event.plain_result("图片下载失败")
                        return
                    img_data = await resp.read()
        except Exception as e:
            yield event.plain_result(f"图片下载失败: {e}")
            return

        try:
            original_img = PILImage.open(BytesIO(img_data)).convert("RGBA")
            
            chromatic_img = self.add_chromatic_aberration(
                original_img, 
                intensity=chromatic_intensity
            )
            
            if glitch_intensity is not None and glitch_intensity > 0:
                chromatic_img = self.add_glitch_effect(chromatic_img, glitch_intensity)
            
            greek_img_path = self.image_dir / f"{greek_name}.png"
            if not greek_img_path.exists():
                available = [f.stem for f in self.image_dir.glob("*.png")]
                available.sort()
                yield event.plain_result(f"未找到 {greek_name}.png\n可用的有: {', '.join(available)}")
                return
            
            greek_img = PILImage.open(greek_img_path).convert("RGBA")
            greek_img = self.resize_greek_image(greek_img, original_img.width, original_img.height)
            
            orig_w, orig_h = chromatic_img.size
            greek_w, greek_h = greek_img.size
            x = (orig_w - greek_w) // 2
            y = (orig_h - greek_h) // 2
            
            combined = PILImage.new("RGBA", chromatic_img.size)
            combined.paste(chromatic_img, (0, 0))
            combined.paste(greek_img, (x, y), greek_img)
            
            timestamp = int(time.time() * 1000)
            random_suffix = random.randint(1000, 9999)
            temp_filename = f"processed_{timestamp}_{random_suffix}.png"
            temp_output_path = self.cache_dir / temp_filename
            
            combined.save(temp_output_path, format="PNG")
            
            yield event.chain_result([Image.fromFileSystem(str(temp_output_path.absolute()))])
        except Exception as e:
            yield event.plain_result(f"图片处理失败: {str(e)}")
            return
