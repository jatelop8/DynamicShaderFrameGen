// Color copy pixel shader - samples source (render resolution backbuffer) into
// target (output resolution). v0.7.8 fallback: when DLSS upscale is not
// executed/failed, copy the game frame (render-res) upscaled to colorOut (4K)
// so downstream always has valid content - no black screen, no size mismatch.
struct VS_OUTPUT
{
	float4 Position : SV_POSITION;
	float2 TexCoord : TEXCOORD;
};

SamplerState LinearClampSampler : register(s0);

#ifdef PSHADER

Texture2D<float4> InputTexture : register(t0);

float4 main(VS_OUTPUT input) : SV_Target
{
	return InputTexture.SampleLevel(LinearClampSampler, input.TexCoord, 0);
}

#endif
