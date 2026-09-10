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
	if (dispatchThreadID.x < min(width, sourceWidth) && dispatchThreadID.y < min(height, sourceHeight))
		DestinationDepth[dispatchThreadID.xy] = SourceDepth[dispatchThreadID.xy];
}
