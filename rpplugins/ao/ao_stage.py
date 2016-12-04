"""

RenderPipeline

Copyright (c) 2014-2016 tobspr <tobias.springer1@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

from panda3d.core import LVecBase2i, Vec4
from rpcore.render_stage import RenderStage
from rpcore.util.bilateral_upscaler import BilateralUpscaler


class AOStage(RenderStage):

    required_inputs = []
    required_pipes = ["GBuffer", "DownscaledDepth", "PreviousFrame::AmbientOcclusion[R8]",
                      "CombinedVelocity", "PreviousFrame::SceneDepth[R32]", "LowPrecisionNormals"]

    @property
    def produced_pipes(self):
        return {"AmbientOcclusion": self.target_resolve.color_tex}

    def create(self):
        self.target = self.create_target("Sample")
        self.target.size = "50%"
        self.target.add_color_attachment(bits=(8, 0, 0, 0))
        self.target.prepare_buffer()

        self.upscaler = BilateralUpscaler(
            self,
            halfres=False,
            source_tex=self.target.color_tex,
            name=self.stage_id + ":Upscale",
            percentage=0.05
        )

        # self.target_upscale = self.create_target("Upscale")
        # self.target_upscale.add_color_attachment(bits=(8, 0, 0, 0))
        # self.target_upscale.prepare_buffer()

        # self.target_upscale.set_shader_input("SourceTex", self.target.color_tex)
        # self.target_upscale.set_shader_input("skyboxColor", Vec4(1))
        # self.target_upscale.set_shader_input("skipSkybox", True)

        self.debug("Blur quality is", self.quality)

        # Low
        pixel_stretch = 2.0
        blur_passes = 1

        if self.quality == "MEDIUM":
            pixel_stretch = 1.0
            blur_passes = 2
        elif self.quality == "HIGH":
            pixel_stretch = 1.0
            blur_passes = 3
        elif self.quality == "ULTRA":
            pixel_stretch = 1.0
            blur_passes = 5

        self.blur_targets = []

        current_tex = self.upscaler.result_tex

        for i in range(blur_passes):
            last_pass = i == blur_passes - 1
            if last_pass and self.enable_small_scale_ao:                
                self.target_detail_ao = self.create_target("DetailAO")
                self.target_detail_ao.add_color_attachment(bits=(8, 0, 0, 0))
                self.target_detail_ao.prepare_buffer()
                self.target_detail_ao.set_shader_input("AOResult", current_tex)
                current_tex = self.target_detail_ao.color_tex

            target_blur_v = self.create_target("BlurV-" + str(i))
            target_blur_v.add_color_attachment(bits=(8, 0, 0, 0))
            target_blur_v.prepare_buffer()

            target_blur_h = self.create_target("BlurH-" + str(i))
            target_blur_h.add_color_attachment(bits=(8, 0, 0, 0))
            target_blur_h.prepare_buffer()

            target_blur_v.set_shader_input("SourceTex", current_tex)
            target_blur_h.set_shader_input("SourceTex", target_blur_v.color_tex)

            target_blur_v.set_shader_input("blur_direction", LVecBase2i(0, 1))
            target_blur_h.set_shader_input("blur_direction", LVecBase2i(1, 0))

            if last_pass and self.enable_small_scale_ao:
                pixel_stretch *= 0.5
            target_blur_v.set_shader_input("pixel_stretch", pixel_stretch)
            target_blur_h.set_shader_input("pixel_stretch", pixel_stretch)

            current_tex = target_blur_h.color_tex
            self.blur_targets += [target_blur_v, target_blur_h]

        self.target_resolve = self.create_target("ResolveAO")
        self.target_resolve.add_color_attachment(bits=(8, 0, 0, 0))
        self.target_resolve.prepare_buffer()
        self.target_resolve.set_shader_input("CurrentTex", current_tex)


    def update(self):
        self.upscaler.update()

    def set_dimensions(self):
        self.upscaler.set_dimensions()

    def reload_shaders(self):
        self.target.shader = self.load_plugin_shader("ao_sample.frag.glsl")
        self.upscaler.set_shaders(
            upscale_shader=self.load_plugin_shader("upscale_ao.frag.glsl"),
            fillin_shader=self.load_plugin_shader("fillin_ao.frag.glsl"),
        )

        blur_shader = self.load_plugin_shader(
            "/$$rp/shader/bilateral_blur.frag.glsl")

        for target in self.blur_targets:
            target.shader = blur_shader
        if self.enable_small_scale_ao:
            self.target_detail_ao.shader = self.load_plugin_shader("small_scale_ao.frag.glsl")

        self.target_resolve.shader = self.load_plugin_shader("resolve_ao.frag.glsl")
