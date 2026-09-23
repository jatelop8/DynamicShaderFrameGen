// CopyDepthGuideCS.hlsl - depth guide conversion (R32_FLOAT) 1:1 subrect copy.
// DynamicShaderFrameGen (GPL-3.0). The engine renders the DRS viewport into the
// top-left of the full-resolution depth texture, so we copy that [0,0,dst] region
// 1:1 into the DLSSNR input (no downscale - keeps original render detail).

Texture2D<float> SourceDepth : register(t0);
RWTexture2D<float> DestinationDepth : register(u0);

[numthreads(8, 8, 1)]
void main(uint3 dispatchThreadID : SV_DispatchThreadID)
{
	uint width;
	uint height;
	uint sourceWidth;
	uint sourceHeight;
	DestinationDepth.GetDimensions(width, height);
	SourceDepth.GetDimensions(sourceWidth, sourceHeight);
	if (dispatchThreadID.x >= width || dispatchThreadID.y >= height)
		return;
	// v1.38: scale-aware guide. width == sourceWidth -> identity mapping, so the
	// DRS 1:1 subrect path is byte-for-byte unchanged; smaller destinations give a
	// nearest-neighbour downscale that stays aligned with the color/mvec downscale.
	const float2 srcUV = (float2(dispatchThreadID.xy) + 0.5f) / float2(width, height);
	const int2 srcTexel = int2(srcUV * float2(sourceWidth, sourceHeight));
	const int2 clamped = clamp(srcTexel, int2(0, 0), int2(sourceWidth - 1, sourceHeight - 1));
	DestinationDepth[dispatchThreadID.xy] = SourceDepth[clamped];
}
