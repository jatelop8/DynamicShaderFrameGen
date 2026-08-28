// Depth copy pixel shader - samples source (render resolution) into target
// (output resolution). v0.7.8: Sample-based upscale - the engine depth is
// render-res (e.g. 1440p under DRS) while the shared texture is output-res (4K).
struct VS_OUTPUT
{
	float4 Position : SV_POSITION;
	float2 TexCoord : TEXCOORD;
};

SamplerState LinearClampSampler : register(s0);

#ifdef PSHADER

Texture2D<float> InputTexture : register(t0);

float main(VS_OUTPUT input) : SV_Target
{
	return InputTexture.SampleLevel(LinearClampSampler, input.TexCoord, 0);
}

#endif
