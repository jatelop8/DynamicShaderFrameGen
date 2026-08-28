// Motion vector copy pixel shader - samples source (render resolution) into
// target (output resolution). v0.7.8: Sample-based upscale - engine mvec is
// render-res while the shared texture is output-res (4K) for FSR3 FG.
// Format: R16G16_FLOAT (signed half).
struct VS_OUTPUT
{
	float4 Position : SV_POSITION;
	float2 TexCoord : TEXCOORD;
};

SamplerState LinearClampSampler : register(s0);

#ifdef PSHADER

Texture2D<float2> InputTexture : register(t0);

float2 main(VS_OUTPUT input) : SV_Target
{
	return InputTexture.SampleLevel(LinearClampSampler, input.TexCoord, 0);
}

#endif
