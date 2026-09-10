// DownscaleCS.hlsl - 2x2 box-filter downscale for DLSSNR color/mvec inputs.
// DynamicShaderFrameGen (GPL-3.0). Used to run the neural renderer at a lower
// input resolution (fewer FP8 tensor ops) and let DLSSNR upsample internally.

Texture2D<float4> Source : register(t0);
RWTexture2D<float4> Destination : register(u0);

[numthreads(8, 8, 1)]
void main(uint3 dispatchThreadID : SV_DispatchThreadID)
{
	uint dstWidth;
	uint dstHeight;
	uint srcWidth;
	uint srcHeight;
	Destination.GetDimensions(dstWidth, dstHeight);
	Source.GetDimensions(srcWidth, srcHeight);
	if (dispatchThreadID.x >= dstWidth || dispatchThreadID.y >= dstHeight)
		return;

	// Map destination texel to source footprint (nearest 2x2 block center).
	const float2 srcUV = (float2(dispatchThreadID.xy) + 0.5f) / float2(dstWidth, dstHeight);
	const float2 src = srcUV * float2(srcWidth, srcHeight) - 0.5f;
	const int2 base = int2(floor(src));
	const float2 frac = src - float2(base);

	const int2 c00 = clamp(base + int2(0, 0), int2(0, 0), int2(srcWidth - 1, srcHeight - 1));
	const int2 c10 = clamp(base + int2(1, 0), int2(0, 0), int2(srcWidth - 1, srcHeight - 1));
	const int2 c01 = clamp(base + int2(0, 1), int2(0, 0), int2(srcWidth - 1, srcHeight - 1));
	const int2 c11 = clamp(base + int2(1, 1), int2(0, 0), int2(srcWidth - 1, srcHeight - 1));

	const float4 s00 = Source[c00];
	const float4 s10 = Source[c10];
	const float4 s01 = Source[c01];
	const float4 s11 = Source[c11];

	// Bilinear weight.
	const float4 top = lerp(s00, s10, frac.x);
	const float4 bottom = lerp(s01, s11, frac.x);
	Destination[dispatchThreadID.xy] = lerp(top, bottom, frac.y);
}
