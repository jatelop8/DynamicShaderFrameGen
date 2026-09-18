// AUTO-GENERATED minimal reproduction of the heartbeat call. Do not edit.
#include <SKSE/SKSE.h>
#include <dxgi.h>
#include <dxgi1_3.h>
#include <chrono>
#include <detours/detours.h>

using namespace SKSE;

namespace probe {
void run() {
	SKSE::log::info(
		"[XRAY] serial={} menu={} world={} edges={} resetTrue={} menuOpen={} reset={} | "
					"consts ok={} fail={} lastR={} | presented all={} world={} menu={} | "
					"real={:.2f}ms | mvecScale=({:.3f},{:.3f}) flags={:#x} | jitter=({:.4f},{:.4f}) "
					"clipDev={:.6f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "
					"prevPos=({:.1f},{:.1f},{:.1f}) | dt min/avg/max={:.2f}/{:.2f}/{:.2f}ms n={} "
					"capUs={} mult(acc/pres)={}/{} longFrames={} cam(ok/inv)={}/{} | "
					"reproj src={} engPrevEqCur={}/{} engPrevZero={} frozen={} "
					"dvd(ok/used)={}/{} err={:.3g} curMag={:.3g} engPrevMag={:.3g} "
					"clipDevMax={:.4f} hist(hit/miss)={}/{} seed={} missGood={} " 
					"det(min/max)={:.3f}/{:.3f} " 
					"fix(src={} dev={:.6g}) "
					"detGuard={} detHold={} tid(a/b/c)={:#x}/{:#x}/{:#x} calls={}/{}/{} | "
					"snap(acc/jmp/re/zero/arr/frozen/shape/rejPct)={}/{}/{}/{}/{}/{}/{} {:.1f}% "
					"shapeRej(own)={:.1f}% "
					"gate(sawDiff/consecRej/frozenRep/resets/id/diff)={}:{}/{}/{}/{}/{} "
					"mapHit(perFrame/unmap)={}/{} dist(last/acc)={:.1f}/{:.1f}",
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0,
		0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0,
		0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0,
		0.0
	);
}
}
