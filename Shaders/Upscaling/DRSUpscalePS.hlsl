// Linux build (dlss-quality): after the DLSS evaluation, depth, refraction normals,
// SAO camera Z and the underwater mask exist only in the DRS render sub-rect (top
// left of the full textures). These shaders stretch them to full size so that
// post-processing and ENB read them correctly once the DRS lock is set.
// After Community Shaders DepthRefractionUpscalePS / UnderwaterMaskUpscalePS
// (https://github.com/doodlum/skyrim-community-shaders, GPL-3.0), without their
// frame-buffer includes: scale, jitter and bounds come from DRSUpscaleCB.
struct VS_OUTPUT
{
	float4 Position : SV_POSITION;
	float2 TexCoord : TEXCOORD;
};

SamplerState LinearClampSampler : register(s0);

cbuffer DRSUpscaleCB : register(b0)
{
	float2 UVScale;   // render sub-rect / full size
	float2 JitterUV;  // jitter in UV of the full texture
	float2 UVMax;     // last valid texel centre inside the sub-rect
	float2 Pad0;
};

float2 SourceUV(float2 a_texCoord)
{
	return clamp(a_texCoord * UVScale - JitterUV, 0.0, UVMax);
}

#if defined(DEPTH)

Texture2D<float4> RefractionNormals : register(t0);
Texture2D<float> DepthTex : register(t1);

struct PS_OUTPUT
{
	float4 RefractionNormals : SV_TARGET0;
	float SAOCameraZ : SV_TARGET1;
	float Depth : SV_Depth;
};

PS_OUTPUT main(VS_OUTPUT input)
{
	PS_OUTPUT psout;
	const float2 uv = SourceUV(input.TexCoord);
	psout.RefractionNormals = RefractionNormals.SampleLevel(LinearClampSampler, uv, 0);
	psout.Depth = DepthTex.SampleLevel(LinearClampSampler, uv, 0);
	psout.SAOCameraZ = psout.Depth;
	return psout;
}

#elif defined(UNDERWATER)

Texture2D<float> UnderwaterMask : register(t0);

float main(VS_OUTPUT input) : SV_TARGET
{
	return UnderwaterMask.SampleLevel(LinearClampSampler, SourceUV(input.TexCoord), 0);
}

#endif
