#include <SKSE/Logger.h>

#include <cstdint>

// Minimal reproduction of the heartbeat call shape:
//   * a chained multi-line format string
//   * many mixed-type arguments
//   * two arguments containing a top-level '>'
//
// The compiler reports the deduced template parameter list in the error
// message.  Comparing that count against the number of format fields tells us
// whether the loss is caused by (a) the argument list, (b) the format string,
// or (c) the SKSE logger's deduction guide.

static std::uint64_t g_u64 = 0;
static std::uint32_t g_u32 = 0;
static int g_i = 0;
static float g_f = 0.0f;
static double g_d = 0.0;
static const char* g_s = "";

void probe()
{
    SKSE::log::info(
        "[PROBE] a={} b={} c={} d={} | "
        "e={:.4f} f={:.4f} | "
        "g={} h={} i={:#x} j={:#x} | "
        "k={:.3f} l={:.3f} m={:#x} n={:.6f} | "
        "o={} p={} q={:.6g} | "
        "r={} s={} t={} u={:.3g} v={:.3g} w={:.3g} | "
        "x={:.4f} y={} z={} aa={} ab={} | "
        "ac={:.3f} ad={:.3f} | "
        "ae={} af={} ag={} ah={} | "
        "ai={} aj={} ak={} al={} | "
        "am={} an={} ao={} ap={} aq={} ar={} as={} at={} | "
        "au={} av={} aw={} ax={} ay={} az={} | "
        "ba={} bb={} bc={} bd={} be={} bf={} bg={} | "
        "bh={} bi={} bj={} bk={} | "
        "bl={:.1f} bm={:.1f} bn={:.1f} | "
        "bo={:.1f} bp={:.1f} | "
        "bq={} br={} bs={} bt={} bu={} bv={} | "
        "bw={} bx={} by={} bz={} ca={} cb={} | "
        "cc={} cd={} ce={} cf={:.1f} cg={:.1f}",
        g_u32, g_u64, g_u64, g_u64,
        g_d, g_f, g_f, g_u32,
        g_f, g_f, g_f, g_f,
        g_f, g_f, g_f, g_f, g_f, g_f,
        g_f, g_f, g_f, g_f,
        g_d, g_d, g_d, g_u64,
        g_u32, g_u32, g_u32,
        g_u64, g_u64, g_s,
        g_u64, g_u64,
        g_u64, g_f, g_f, g_f, g_f,
        g_u64, g_u64, g_u64, g_u64,
        g_u64, g_u64, g_f, g_f,
        g_u64, g_u64, g_u32, g_u32, g_u32,
        g_u64, g_u64, g_u64, g_u64, g_u64,
        g_u64, g_u64, g_u64, g_u64, g_d, g_i,
        g_u32, g_u64, g_u64, g_u64,
        g_u64, g_u64, g_u64,
        g_f, g_f,
        g_u64, g_u64, g_u64, g_u64,
        g_u64, g_u64, g_u64,
        g_f, g_f);
}
