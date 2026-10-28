/* ncmelt official site interactions */
(() => {
    "use strict";

    const header = document.getElementById("site-header");
    const menuToggle = document.querySelector(".menu-toggle");
    const mobileNav = document.getElementById("mobile-nav");
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ------------------------------------------------------------
    // Header / mobile navigation
    // ------------------------------------------------------------
    const setMenu = (open, returnFocus = false) => {
        if (!menuToggle || !mobileNav || !header) return;
        mobileNav.hidden = !open;
        header.classList.toggle("is-open", open);
        document.body.classList.toggle("nav-open", open);
        menuToggle.setAttribute("aria-expanded", String(open));
        menuToggle.setAttribute("aria-label", open ? "关闭导航菜单" : "打开导航菜单");
        if (!open && returnFocus) menuToggle.focus();
    };

    if (menuToggle && mobileNav) {
        menuToggle.addEventListener("click", () => {
            setMenu(mobileNav.hidden);
        });

        mobileNav.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => setMenu(false));
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth > 980 && !mobileNav.hidden) setMenu(false);
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && mobileNav && !mobileNav.hidden) {
            setMenu(false, true);
        }
    });

    const syncHeader = () => {
        if (header) header.classList.toggle("is-scrolled", window.scrollY > 8);
    };
    syncHeader();
    window.addEventListener("scroll", syncHeader, { passive: true });

    // ------------------------------------------------------------
    // Reveal on scroll
    // ------------------------------------------------------------
    const revealItems = Array.from(document.querySelectorAll(".reveal"));
    if (!prefersReducedMotion && "IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver(
            (entries, observer) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                });
            },
            { rootMargin: "0px 0px -8% 0px", threshold: 0.06 }
        );
        revealItems.forEach((item) => revealObserver.observe(item));
    } else {
        revealItems.forEach((item) => item.classList.add("is-visible"));
    }

    // ------------------------------------------------------------
    // Screenshot state tabs
    // ------------------------------------------------------------
    const shotImage = document.getElementById("shot-image");
    const shotState = document.getElementById("shot-state-text");
    const shotCaption = document.getElementById("shot-caption-text");
    const shotPanel = document.getElementById("shot-panel");
    const shotTabs = Array.from(document.querySelectorAll(".shot-tab"));
    const shots = {
        ready: {
            src: "assets/screenshot-ready.webp",
            srcset: "assets/screenshot-ready-1280.webp 1280w, assets/screenshot-ready.webp 1600w",
            alt: "ncmelt 主界面：队列中 4 个 NCM 文件等待转换，右侧选择 MP3 320 kbps。",
            state: "就绪",
            caption: "转换前 / 4 个文件待处理"
        },
        done: {
            src: "assets/screenshot-done.webp",
            srcset: "assets/screenshot-done-1280.webp 1280w, assets/screenshot-done.webp 1600w",
            alt: "ncmelt 转换完成界面：4 首全部完成，队列状态显示完成，输出目录已写入。",
            state: "全部完成",
            caption: "转换后 / 4 首全部完成"
        }
    };
    let activeShot = "ready";

    const selectShot = (name) => {
        if (!shotImage || !shots[name] || name === activeShot) return;
        const shot = shots[name];
        activeShot = name;

        shotTabs.forEach((tab) => {
            const selected = tab.dataset.shot === name;
            tab.setAttribute("aria-selected", String(selected));
            tab.tabIndex = selected ? 0 : -1;
        });
        if (shotPanel) {
            const activeTab = document.getElementById(`shot-tab-${name}`);
            if (activeTab) shotPanel.setAttribute("aria-labelledby", activeTab.id);
        }

        if (shotState) shotState.textContent = shot.state;
        if (shotCaption) shotCaption.textContent = shot.caption;
        shotImage.classList.add("is-switching");

        const apply = () => {
            shotImage.src = shot.src;
            shotImage.srcset = shot.srcset;
            shotImage.alt = shot.alt;
            const reveal = () => shotImage.classList.remove("is-switching");
            if (shotImage.complete) {
                window.setTimeout(reveal, 40);
            } else {
                shotImage.addEventListener("load", reveal, { once: true });
                shotImage.addEventListener("error", reveal, { once: true });
            }
        };

        const preload = new Image();
        preload.onload = apply;
        preload.onerror = apply;
        preload.src = shot.src;
    };

    shotTabs.forEach((tab, index) => {
        tab.addEventListener("click", () => selectShot(tab.dataset.shot));
        tab.addEventListener("keydown", (event) => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            let next = index;
            if (event.key === "ArrowRight") next = (index + 1) % shotTabs.length;
            if (event.key === "ArrowLeft") next = (index - 1 + shotTabs.length) % shotTabs.length;
            if (event.key === "Home") next = 0;
            if (event.key === "End") next = shotTabs.length - 1;
            shotTabs[next].focus();
            selectShot(shotTabs[next].dataset.shot);
        });
    });

    // ------------------------------------------------------------
    // Output format selector
    // ------------------------------------------------------------
    const formats = {
        mp3: {
            mark: "MP3",
            kind: "LOSSY",
            title: "兼容性最好，日常播放首选",
            subtitle: "MP3 · 有损压缩",
            badge: "推荐",
            desc: "几乎每台设备都能播放。固定码率适合统一归档，V0 动态码率则在体积和听感之间取平衡。",
            qualities: [
                { name: "320 kbps", note: "固定码率 · 细节最完整", default: true, badge: "默认" },
                { name: "256 kbps", note: "固定码率 · 音质与体积均衡" },
                { name: "192 kbps", note: "固定码率 · 日常收听" },
                { name: "128 kbps", note: "固定码率 · 体积最小" },
                { name: "V0 动态", note: "可变码率 · 平均约 245 kbps" }
            ],
            note: "适合车载、手机与旧播放器"
        },
        flac: {
            mark: "FLAC",
            kind: "LOSSLESS",
            title: "无损归档，完整保留音频",
            subtitle: "FLAC · 无损压缩",
            badge: "无损",
            desc: "把解密出的无损音频原样保留，只做无损压缩。文件比 WAV 小，适合长期收藏和后续转码。",
            qualities: [
                { name: "标准压缩", note: "无损 · 推荐", default: true, badge: "默认" },
                { name: "最高压缩", note: "无损 · 文件更小，编码更慢" },
                { name: "快速压缩", note: "无损 · 编码最快" }
            ],
            note: "适合长期归档、Hi-Fi 播放"
        },
        wav: {
            mark: "WAV",
            kind: "PCM",
            title: "未压缩，编辑软件最省心",
            subtitle: "WAV · PCM",
            badge: "编辑",
            desc: "不做任何有损压缩，直接输出 PCM。文件最大，但兼容几乎所有音频编辑和采样工具。",
            qualities: [
                { name: "16-bit PCM", note: "CD 级精度 · 兼容性最好", default: true, badge: "默认" },
                { name: "24-bit PCM", note: "更高动态范围 · 体积更大" }
            ],
            note: "适合剪辑、混音与采样"
        },
        m4a: {
            mark: "M4A",
            kind: "AAC-LC",
            title: "手机和 Apple 设备友好",
            subtitle: "M4A · AAC-LC",
            badge: "移动端",
            desc: "AAC-LC 在较低码率下保持不错的听感，iPhone、iPad 和大多数移动播放器都能直接打开。",
            qualities: [
                { name: "256 kbps", note: "AAC-LC · 细节最完整", default: true, badge: "默认" },
                { name: "192 kbps", note: "AAC-LC · 移动收听均衡" },
                { name: "128 kbps", note: "AAC-LC · 体积最小" }
            ],
            note: "适合 iPhone、iPad 与移动播放"
        },
        ogg: {
            mark: "OGG",
            kind: "VORBIS",
            title: "开源格式，体积与音质均衡",
            subtitle: "OGG · Vorbis",
            badge: "开源",
            desc: "Vorbis 在中等码率下表现自然，适合开源播放器、游戏和需要控制体积的曲库。",
            qualities: [
                { name: "Q8", note: "Vorbis · 最高音质" },
                { name: "Q6", note: "Vorbis · 音质与体积均衡", default: true, badge: "默认" },
                { name: "Q4", note: "Vorbis · 更小体积" }
            ],
            note: "适合开源播放器与游戏音频"
        }
    };

    const formatTabs = Array.from(document.querySelectorAll(".format-tab"));
    const formatPanel = document.getElementById("format-panel");
    const formatMark = document.getElementById("format-mark");
    const formatKind = document.getElementById("format-kind");
    const formatTitle = document.getElementById("format-title");
    const formatSubtitle = document.getElementById("format-subtitle");
    const formatBadge = document.getElementById("format-badge");
    const formatDesc = document.getElementById("format-desc");
    const formatNote = document.getElementById("format-note");
    const formatWatermark = document.getElementById("format-watermark");
    const qualityList = document.getElementById("quality-list");
    let activeFormat = "mp3";

    const makeQuality = (quality) => {
        const item = document.createElement("li");
        item.className = "quality-item" + (quality.default ? " is-default" : "");

        const top = document.createElement("span");
        top.className = "quality-top";
        const name = document.createElement("b");
        name.textContent = quality.name;
        top.append(name);
        if (quality.badge) {
            const badge = document.createElement("em");
            badge.textContent = quality.badge;
            top.append(badge);
        }

        const note = document.createElement("span");
        note.textContent = quality.note;
        item.append(top, note);
        return item;
    };

    const selectFormat = (name, moveFocus = false) => {
        const data = formats[name];
        if (!data) return;
        activeFormat = name;

        formatTabs.forEach((tab) => {
            const selected = tab.dataset.format === name;
            tab.setAttribute("aria-selected", String(selected));
            tab.tabIndex = selected ? 0 : -1;
            if (selected && moveFocus) tab.focus();
        });

        if (formatPanel) {
            const activeTab = document.getElementById(`format-tab-${name}`);
            if (activeTab) formatPanel.setAttribute("aria-labelledby", activeTab.id);
        }
        if (formatMark) formatMark.textContent = data.mark;
        if (formatKind) formatKind.textContent = data.kind;
        if (formatTitle) formatTitle.textContent = data.title;
        if (formatSubtitle) formatSubtitle.textContent = data.subtitle;
        if (formatBadge) formatBadge.textContent = data.badge;
        if (formatDesc) formatDesc.textContent = data.desc;
        if (formatNote) formatNote.textContent = data.note;
        if (formatWatermark) formatWatermark.textContent = data.mark;
        if (qualityList) {
            qualityList.replaceChildren(...data.qualities.map(makeQuality));
        }
    };

    formatTabs.forEach((tab, index) => {
        tab.addEventListener("click", () => selectFormat(tab.dataset.format));
        tab.addEventListener("keydown", (event) => {
            if (!["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            let next = index;
            if (event.key === "ArrowDown" || event.key === "ArrowRight") {
                next = (index + 1) % formatTabs.length;
            }
            if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
                next = (index - 1 + formatTabs.length) % formatTabs.length;
            }
            if (event.key === "Home") next = 0;
            if (event.key === "End") next = formatTabs.length - 1;
            selectFormat(formatTabs[next].dataset.format, true);
        });
    });

    // Keep the initial DOM and the data in sync (also handles no-JS fallback).
    if (formatTabs.length) selectFormat(activeFormat);

    // ------------------------------------------------------------
    // Copy CLI examples
    // ------------------------------------------------------------
    const cliCommands = [
        "ncmelt input.ncm -o output.mp3",
        "ncmelt a.ncm b.ncm -o D:\\Music --format flac --quality max",
        "ncmelt input.ncm -o output.m4a --quality 256"
    ].join("\n");

    const toast = document.getElementById("toast");
    let toastTimer = 0;
    const showToast = (message) => {
        if (!toast) return;
        window.clearTimeout(toastTimer);
        toast.textContent = message;
        toast.classList.add("is-visible");
        toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2200);
    };

    const fallbackCopy = (text) => {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.top = "-1000px";
        textarea.style.opacity = "0";
        document.body.append(textarea);
        textarea.select();
        let copied = false;
        try {
            copied = document.execCommand("copy");
        } catch (_error) {
            copied = false;
        }
        textarea.remove();
        return copied;
    };

    const copyButton = document.querySelector("[data-copy-command]");
    if (copyButton) {
        const copyLabel = copyButton.querySelector("span");
        copyButton.addEventListener("click", async () => {
            let copied = false;
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(cliCommands);
                    copied = true;
                }
            } catch (_error) {
                copied = false;
            }
            if (!copied) copied = fallbackCopy(cliCommands);

            if (copied) {
                showToast("命令行示例已复制");
                if (copyLabel) {
                    const original = copyLabel.textContent;
                    copyLabel.textContent = "已复制";
                    window.setTimeout(() => {
                        copyLabel.textContent = original;
                    }, 1800);
                }
            } else {
                showToast("复制失败，请手动选择命令");
            }
        });
    }

    // ------------------------------------------------------------
    // FAQ: keep the page tidy with one open item at a time
    // ------------------------------------------------------------
    const faqItems = Array.from(document.querySelectorAll(".faq details"));
    faqItems.forEach((item) => {
        item.addEventListener("toggle", () => {
            if (!item.open) return;
            faqItems.forEach((other) => {
                if (other !== item) other.open = false;
            });
        });
    });
})();
