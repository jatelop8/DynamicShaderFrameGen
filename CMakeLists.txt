cmake_minimum_required(VERSION 3.24)
project(DynamicShaderFrameGen)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 独立 CommonLibSSE-NG（官方仓库）
if(NOT DEFINED COMMONLIB_DIR)
    set(COMMONLIB_DIR "D:/Modding/CommonLibSSE-NG")
endif()

# vcpkg 预装库（手动安装，不走 vcpkg 自动安装——规避 VS 检测 bug）
if(NOT DEFINED VCPKG_PREFIX)
    set(VCPKG_PREFIX "E:/vcpkg-full/installed/x64-windows-static-md")
endif()

# NVIDIA Streamline SDK（新版 2.12 头文件，支持 DLSSG/Reflex；旧版 CS extern 头缺 DLSS5 API）
if(NOT DEFINED STREAMLINE_DIR)
    set(STREAMLINE_DIR "D:/Modding/extern/Streamline")
endif()

# AMD FidelityFX SDK（头文件，创建 FG swapchain 用；本地浅克隆）
if(NOT DEFINED FFX_DIR)
    set(FFX_DIR "D:/Modding/extern/FidelityFX-SDK")
endif()

set(CommonLibPath "${COMMONLIB_DIR}")
set(CommonLibName "CommonLibSSE")

add_library(${PROJECT_NAME} SHARED
    src/main.cpp
    src/FrameGen.cpp
    src/DX12SwapChain.cpp
    src/Streamline.cpp
    src/FidelityFX.cpp
    src/ImguiMenu.cpp
    # v0.7：Dear ImGui 源码（vcpkg 下载被代理拦，直接 extern 编译）
    extern/imgui/imgui.cpp
    extern/imgui/imgui_draw.cpp
    extern/imgui/imgui_tables.cpp
    extern/imgui/imgui_widgets.cpp
    extern/imgui/imgui_demo.cpp
    extern/imgui/backends/imgui_impl_dx11.cpp
    extern/imgui/backends/imgui_impl_win32.cpp
    src/version.rc
)

target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_23)

target_compile_definitions(${PROJECT_NAME} PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN SKYRIM NV_WINDOWS)

target_compile_options(${PROJECT_NAME} PRIVATE
    /MP
    /W4
    /wd4200
    /wd4819
    /wd4996
    /wd4471
)

target_compile_options(${PROJECT_NAME} PUBLIC
    "$<$<CONFIG:DEBUG>:/fp:strict;/ZI;/Od;/Gy>"
    "$<$<CONFIG:RELEASE>:/Zi;/fp:fast;/GL;/Gy-;/O2;/Ob2;/Oi;/Ot;/Oy>"
)

# CommonLibSSE-NG 源码
set(_CMAKE_CXX_IPO_MAY_BE_SUPPORTED_BY_COMPILER FALSE CACHE INTERNAL "skip IPO check")
set(_CMAKE_C_IPO_MAY_BE_SUPPORTED_BY_COMPILER FALSE CACHE INTERNAL "skip IPO check")
add_subdirectory(${CommonLibPath} ${CommonLibName} EXCLUDE_FROM_ALL)

# 依赖：spdlog / directxtk（CommonLibSSE-NG 需要），从 vcpkg 预装库查找
find_package(spdlog CONFIG REQUIRED)
find_package(directxtk CONFIG REQUIRED)

target_include_directories(${PROJECT_NAME} PRIVATE "${VCPKG_PREFIX}/include")
target_include_directories(${PROJECT_NAME} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/extern/imgui")
target_include_directories(${PROJECT_NAME} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/extern/imgui/backends")
target_include_directories(${PROJECT_NAME} PRIVATE "${STREAMLINE_DIR}/include")
target_include_directories(${PROJECT_NAME} PRIVATE "${FFX_DIR}/Kits")
target_include_directories(${PROJECT_NAME} PRIVATE "D:/Modding/skyrim-community-shaders-dxr/extern/FidelityFX-SDK/framework/cauldron/framework/libs/pix")

target_link_libraries(${PROJECT_NAME} PRIVATE CommonLibSSE::CommonLibSSE spdlog::spdlog)
target_link_libraries(${PROJECT_NAME} PRIVATE d3d12.lib d3d11.lib dxgi.lib d3dcompiler.lib delayimp.lib)
# v0.7.15：Detours（函数开头 detour，CS 同款）——MenuManagerDrawInterfaceStart hook。
# write_branch 只能重定向现有 jmp/call，不能做函数 detour（原指令会丢 → 崩溃实锤）
target_link_libraries(${PROJECT_NAME} PRIVATE "${VCPKG_PREFIX}/lib/detours.lib")

# v0.5.2：d3d11 延迟加载（/DELAYLOAD）——ENB 整合包根因修复：
# 游戏目录有 ENB 的 d3d11.dll 代理，SKSE 加载本插件时若静态解析 d3d11.dll →
# 触发 ENB 代理在插件加载阶段初始化失败 → LoadLibrary 整体失败（skse64.log
# "no version data (handle 0)" 不加载）。delayload 后 SKSE 加载零 d3d11 依赖，
# 运行时首次调用（游戏 D3D 初始化后，ENB 代理已正常加载）才解析。
# v0.5.17：d3d12.dll 恢复静态导入（ENB 不代理 d3d12，无冲突）——SL interposer
# 的 IAT hook 需要拦 D3D12CreateCommandQueue（dlss_g 插件靠它记录 queue；
# delayload 的 d3d12 走 delay-import thunk，IAT hook 拦不到 → 插件 queue 槽
# null → Allocate 时 0xC0000005 崩溃）。
target_link_options(${PROJECT_NAME} PRIVATE "/DELAYLOAD:d3d11.dll")

# 生成后复制到游戏 Data 目录（-DPLUGIN_DEPLOY_DIR 指定）
if(DEFINED PLUGIN_DEPLOY_DIR)
    add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_FILE:${PROJECT_NAME}>
            "${PLUGIN_DEPLOY_DIR}/SKSE/Plugins/DynamicShaderFrameGen.dll"
        # v0.5.4: deploy INI + runtime DLLs too. MO2 rule: mod root == game Data tree,
        # so NO "Data/" prefix anywhere (a Data/ prefix maps to Data/Data/... and
        # the game never finds the files - verified 2026-08-28 "No INI found").
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_SOURCE_DIR}/SKSE/Plugins/DynamicShaderFrameGen.ini"
            "${PLUGIN_DEPLOY_DIR}/SKSE/Plugins/DynamicShaderFrameGen.ini"
        COMMAND ${CMAKE_COMMAND} -E copy_directory
            "${CMAKE_SOURCE_DIR}/Shaders"
            "${PLUGIN_DEPLOY_DIR}/Shaders"
    )
endif()
