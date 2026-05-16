export const extractFilename = (header, fallback) => {
    if (!header) return fallback;

    const utf8 = /filename\*=UTF-8''([^;\s]+)/i.exec(header);
    if (utf8) {
        try { return decodeURIComponent(utf8[1]); }
        catch { /* fallthrough */ }
    }

    const simple = /filename="?([^";]+?)"?(?:;|$)/i.exec(header);
    return simple ? simple[1] : fallback;
};

export const triggerDownload = (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
};
