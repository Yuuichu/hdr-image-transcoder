const DEFAULT_LANGUAGE = "zh-Hans";
const LANGUAGE_STORAGE_KEY = "hdrTranscoderLanguage";

const I18N = {
  "zh-Hans": {
    documentTitle: "HDR 图像转码器",
    unknown: "未知",
    yes: "是",
    no: "否",
    present: "存在",
    notDetected: "未检测到",
    passed: "通过",
    failed: "失败",
    ui: {
      brandTitle: "HDR 图像转码器",
      brandSubtitle: "专业 HDR 静态图像转码与验证工作台。",
      language: "语言",
      addImages: "添加图像",
      addFolder: "添加文件夹",
      outputFolder: "输出目录",
      selfCheck: "运行自检",
      start: "开始",
      cancel: "取消",
      clear: "清空",
      useDefaultOutput: "使用默认输出位置",
      fileQueue: "文件队列",
      settings: "转码设置",
      inspector: "检查器",
      log: "日志",
      all: "全部",
      warnings: "警告",
      errors: "错误",
      expand: "展开",
      collapse: "折叠",
      outputFormat: "输出格式",
      fidelity: "保真模式",
      jxlMode: "JPEG XL HDR 模式",
      losslessJxl: "无损 JPEG XL",
      uhdrSection: "Ultra HDR JPEG",
      uhdrBackend: "Ultra HDR 后端",
      gainmapScale: "Gainmap 缩放",
      targetPeak: "目标峰值亮度 nits",
      knownPqTiff: "已确认 BT.2020 PQ TIFF 输入",
      gainmapSection: "Gainmap AVIF",
      headroomMode: "Headroom 模式",
      displayHdrSection: "Display HDR",
      displayHdrNote: "标准 AVIF 和 HEIF HDR 会编码为 Rec.2020 PQ 显示交付文件。",
      baseHeadroom: "基础图 Headroom",
      quality: "质量",
      speed: "速度",
      verifyFidelity: "验证保真度",
      debugOverlay: "调试信息叠加图",
      infoJson: "输出 Info JSON",
      outputNaming: "输出命名",
      prefix: "前缀",
      suffix: "后缀",
      find: "查找",
      replaceWith: "替换为",
      renamePattern: "重命名模式",
      startIndex: "起始序号",
      padding: "补零位数",
      defaultOutputLocation: "默认输出位置",
      queueEmpty: "添加图像或文件夹后，可在这里检查并转换。",
    },
    aria: {
      format: "解释输出格式",
      fidelity: "解释保真模式",
      jxlMode: "解释 JPEG XL 模式",
      lossless: "解释无损 JPEG XL",
      uhdrBackend: "解释 Ultra HDR 后端",
      gainmapScale: "解释 gainmap 缩放",
      targetPeak: "解释目标峰值亮度",
      pqTiff: "解释 BT.2020 PQ TIFF",
      gainmapHeadroomMode: "解释 gainmap headroom 模式",
      baseHeadroom: "解释基础图 headroom",
      quality: "解释质量",
      speed: "解释速度",
      verifyFidelity: "解释验证保真度",
      debugOverlay: "解释调试叠加图",
      infoJson: "解释 Info JSON",
      outputNaming: "解释输出命名",
    },
    placeholders: {
      prefix: "HDR_",
      suffix: "_converted",
      find: "Screenshot",
      replace: "HDR",
      pattern: "Forza_HDR_{n}",
    },
    formats: {
      jxl: "JPEG XL 母版",
      avif: "标准 HDR AVIF",
      heif: "HEIF HDR",
      ultrahdr: "Ultra HDR JPEG",
      gainmap: "Gainmap AVIF",
    },
    options: {
      jxlLinear: "线性归档 (scRGB)",
      jxlPq: "显示 HDR (Rec.2020 PQ)",
      auto: "自动",
      imagecodecs: "imagecodecs",
      libultrahdr: "libultrahdr",
      sourcePeak: "源峰值",
    },
    fidelity: {
      master: "母版",
      display: "显示 HDR",
      compat: "兼容",
    },
    status: {
      Idle: "空闲",
      Running: "运行中",
      Done: "完成",
      Canceled: "已取消",
      Error: "错误",
      Unavailable: "不可用",
      "Runtime Error": "运行环境错误",
      "No Files": "无文件",
      "Needs Input": "需要输入",
    },
    queueStatus: {
      queued: "排队",
      inspecting: "分析中",
      ready: "就绪",
      running: "转换中",
      done: "完成",
      error: "错误",
    },
    badges: {
      inspectError: "检查错误",
      gainmap: "Gainmap",
      sdr: "SDR",
      inspecting: "分析中",
      pending: "待处理",
    },
    infoLabels: {
      file: "文件",
      format: "格式",
      dimensions: "尺寸",
      fileSize: "文件大小",
      color: "色彩",
      colorSource: "色彩来源",
      cicp: "CICP/nclx",
      hdr: "HDR",
      rgbPeak: "RGB 峰值",
      headroom: "Headroom",
      gainMap: "Gain Map",
      baseHeadroom: "基础 Headroom",
      altHeadroom: "替代 Headroom",
      error: "错误",
      warning: "警告",
      output: "输出",
      peak: "峰值",
      verify: "验证",
    },
    help: {
      format: {
        title: "输出格式",
        body: "选择容器和 HDR 交付方式。JPEG XL 线性模式最适合做归档母版；AVIF/HEIF 是标准 PQ 显示文件；Ultra HDR 和 Gainmap AVIF 更偏兼容路径，带 SDR 基础图。",
      },
      fidelity: {
        title: "保真模式",
        body: "母版保留便于后期处理的线性 HDR；显示 HDR 生成可直接观看的 PQ 文件；兼容模式生成带 gainmap 的文件，适合需要 SDR fallback 的阅读器。",
      },
      "jxl-mode": {
        title: "JPEG XL HDR 模式",
        body: "线性归档会保存类似 scRGB 的线性 HDR，更适合作母版。Rec.2020 PQ 更适合显示和分享，但不是最严格的归档路径。",
      },
      lossless: {
        title: "无损 JPEG XL",
        body: "在线性归档模式下，无损会保持严格母版行为。面向显示的转换中，无损只作用在 HDR 转换和色彩转换之后。",
      },
      "uhdr-backend": {
        title: "Ultra HDR 后端",
        body: "自动模式会优先使用 libultrahdr，找不到时回退到 imagecodecs。专门的已知 PQ TIFF 路径需要 libultrahdr；imagecodecs 是旧 fallback 路径。",
      },
      "uhdr-gainmap-scale": {
        title: "Gainmap 缩放",
        body: "控制 Ultra HDR gainmap 的分辨率。数值越低细节越多、体积越大。2 是推荐的兼容默认值。",
      },
      "target-peak": {
        title: "目标峰值亮度",
        body: "设置 libultrahdr 编码时的目标 HDR 显示峰值。已知 PQ TIFF 工作流默认使用 1000 nits。",
      },
      "pq-tiff": {
        title: "已知 BT.2020 PQ TIFF",
        body: "只在你能确认 TIFF RGB 样本是 BT.2020 原色且使用 PQ/ST.2084 传递函数时开启。普通 TIFF 不要开启。",
      },
      "gainmap-headroom-mode": {
        title: "Gainmap Headroom 模式",
        body: "源峰值会根据解码出的 HDR peak 写入 Alternate headroom，是保真路径。自动模式保留 libavif 自己计算出的元数据。",
      },
      "base-headroom": {
        title: "基础图 Headroom",
        body: "控制 gainmap 输出中 SDR base tone mapping 保留多少高光细节。数值越高越能保留高光结构，但 SDR 对比可能下降。",
      },
      quality: {
        title: "质量",
        body: "数值越高通常细节越多、体积越大。做保真验证和兼容性排查时建议使用 100。",
      },
      speed: {
        title: "速度",
        body: "编码器 effort。0 最慢但压缩效率最好；10 最快。它不能替代质量参数。",
      },
      "debug-overlay": {
        title: "调试信息叠加图",
        body: "额外写出带诊断文字的 SDR PNG sidecar，不会修改最终输出图像。",
      },
      "info-json": {
        title: "输出 Info JSON",
        body: "写出包含格式、CICP、gainmap、peak、验证结果和 inspector 元数据的 sidecar JSON。排查 HDR 兼容性时建议保持开启。",
      },
      "verify-fidelity": {
        title: "验证保真度",
        body: "编码后运行项目内验证。如果元数据或重建 peak 超出项目阈值，转换会失败。",
      },
      "output-naming": {
        title: "输出命名模式",
        body: "使用 {name} 代表原始文件名，使用 {n} 代表序号。前缀、后缀、查找和替换会在写出文件前应用。",
      },
    },
    messages: {
      helpDefault: "点击选项旁边的 ? 查看说明。",
      noImagesSelected: "未选择图像。",
      queuedCount: "已加入 {count} 张图像。",
      noImageInfo: "没有可用的图像信息。",
      inspecting: "正在分析所选图像元数据...",
      selectImage: "选择队列中的图像以检查技术元数据。",
      metadataNotLoaded: "元数据尚未加载。",
      reportEmpty: "启用 Info JSON 后，转换报告会显示在这里。",
      noLogs: "暂无日志。",
      logSummary: "共 {total} 条日志，{warnings} 条警告，{errors} 条错误。",
      runningProgress: "运行中 {current}/{total}",
      runtimeCheckFailed: "运行环境检查失败。",
      runtimeReady: "运行环境就绪。Python {version}；内置工具已找到；{uhdrText}。",
      uhdrAvailable: "libultrahdr 可用",
      uhdrMissing: "未找到可选的 libultrahdr DLL",
      runtimeError: "运行环境错误：{issue}",
      runtimeSelfCheckFailed: "运行环境自检失败：{issue}",
      checkingRuntime: "正在检查运行环境...",
      selectAtLeastOne: "请先选择至少一个图像文件。",
      selectInputFirst: "请先选择输入文件或文件夹。",
      qualityRange: "质量必须在 0 到 100 之间。",
      speedRange: "速度必须在 0 到 10 之间。",
      headroomPositive: "基础 headroom 必须大于 0。",
      gainmapScaleRange: "Ultra HDR gainmap 缩放必须在 1 到 128 之间。",
      targetPeakRange: "Ultra HDR 目标峰值必须在 203 到 10000 nits 之间。",
      unknownUhdrBackend: "未知的 Ultra HDR 后端。",
      unknownJxlMode: "未知的 JPEG XL 模式。",
      unknownFidelity: "未知的保真模式。",
      unknownGainmapHeadroom: "未知的 gainmap headroom 模式。",
      nameStartRange: "起始序号必须大于或等于 0。",
      namePaddingRange: "补零位数必须大于或等于 0。",
      pqTiffWarning: "BT.2020 PQ TIFF 模式假定未标记的 TIFF RGB 样本确实是 BT.2020 PQ/ST.2084。普通 TIFF 请保持关闭。",
      uhdrAutoWarning: "libultrahdr 不可用。自动模式会回退到旧的 imagecodecs Ultra HDR 路径。",
      uhdrLibWarning: "libultrahdr 不可用。请配置 HDR_TRANSCODER_UHDR_DLL 或 tools/libultrahdr/uhdr.dll，否则转换会失败。",
      outputFolderSelected: "已选择输出目录。",
      defaultOutputUsed: "将使用默认输出位置。",
      queueCleared: "队列已清空。",
      oneImageSelected: "已选择 1 张图像。",
      imagesSelected: "已选择 {count} 张图像。",
      noSupportedFiles: "这个文件夹里没有找到支持的图像文件。",
      folderSelected: "已选择文件夹，找到 {count} 个支持的图像文件。",
      conversionStarted: "转换开始",
      conversionRunning: "转换正在运行。",
      conversionCanceled: "转换已取消。",
      cancelRequested: "已请求取消。",
      conversionFailed: "转换失败。",
      conversionEnded: "转换结束。",
      finished: "已完成。",
      finishedChecked: "已完成。检查了 {count} 个输出路径。",
      overwriteExtra: "，以及另外 {count} 个",
      overwriteConfirm: "已有 {count} 个输出文件存在：\n\n{names}{extra}\n\n是否覆盖？",
      infoReadFailed: "无法读取输出 Info JSON：{message}",
      preloadUnavailable: "Electron preload API 不可用。请用 npm start 启动此界面。",
    },
  },
  en: {
    documentTitle: "HDR Image Transcoder",
    unknown: "Unknown",
    yes: "Yes",
    no: "No",
    present: "Present",
    notDetected: "Not detected",
    passed: "Passed",
    failed: "Failed",
    ui: {
      brandTitle: "HDR Image Transcoder",
      brandSubtitle: "Professional HDR still image conversion and verification.",
      language: "Language",
      addImages: "Add Images",
      addFolder: "Add Folder",
      outputFolder: "Output Folder",
      selfCheck: "Self Check",
      start: "Start",
      cancel: "Cancel",
      clear: "Clear",
      useDefaultOutput: "Use default output location",
      fileQueue: "File Queue",
      settings: "Settings",
      inspector: "Inspector",
      log: "Log",
      all: "All",
      warnings: "Warnings",
      errors: "Errors",
      expand: "Expand",
      collapse: "Collapse",
      outputFormat: "Output Format",
      fidelity: "Fidelity",
      jxlMode: "JPEG XL HDR Mode",
      losslessJxl: "Lossless JPEG XL",
      uhdrSection: "Ultra HDR JPEG",
      uhdrBackend: "Ultra HDR Backend",
      gainmapScale: "Gainmap Scale",
      targetPeak: "Target Peak Nits",
      knownPqTiff: "Known BT.2020 PQ TIFF input",
      gainmapSection: "Gainmap AVIF",
      headroomMode: "Headroom Mode",
      displayHdrSection: "Display HDR",
      displayHdrNote: "Standard AVIF and HEIF HDR are encoded as Rec.2020 PQ delivery files.",
      baseHeadroom: "Base Headroom",
      quality: "Quality",
      speed: "Speed",
      verifyFidelity: "Verify Fidelity",
      debugOverlay: "Debug Info Overlay",
      infoJson: "Output Info JSON",
      outputNaming: "Output Naming",
      prefix: "Prefix",
      suffix: "Suffix",
      find: "Find",
      replaceWith: "Replace With",
      renamePattern: "Rename Pattern",
      startIndex: "Start",
      padding: "Padding",
      defaultOutputLocation: "Default output location",
      queueEmpty: "Add images or a folder to inspect and convert.",
    },
    aria: {
      format: "Explain output format",
      fidelity: "Explain fidelity modes",
      jxlMode: "Explain JPEG XL mode",
      lossless: "Explain lossless JPEG XL",
      uhdrBackend: "Explain Ultra HDR backend",
      gainmapScale: "Explain gainmap scale",
      targetPeak: "Explain target peak nits",
      pqTiff: "Explain BT.2020 PQ TIFF",
      gainmapHeadroomMode: "Explain gainmap headroom mode",
      baseHeadroom: "Explain base headroom",
      quality: "Explain quality",
      speed: "Explain speed",
      verifyFidelity: "Explain verify fidelity",
      debugOverlay: "Explain debug overlay",
      infoJson: "Explain info JSON",
      outputNaming: "Explain output naming",
    },
    placeholders: {
      prefix: "HDR_",
      suffix: "_converted",
      find: "Screenshot",
      replace: "HDR",
      pattern: "Forza_HDR_{n}",
    },
    formats: {
      jxl: "JPEG XL Master",
      avif: "Standard HDR AVIF",
      heif: "HEIF HDR",
      ultrahdr: "Ultra HDR JPEG",
      gainmap: "Gainmap AVIF",
    },
    options: {
      jxlLinear: "Linear Archive (scRGB)",
      jxlPq: "Display HDR (Rec.2020 PQ)",
      auto: "Auto",
      imagecodecs: "imagecodecs",
      libultrahdr: "libultrahdr",
      sourcePeak: "Source Peak",
    },
    fidelity: {
      master: "Master",
      display: "Display HDR",
      compat: "Compat",
    },
    status: {
      Idle: "Idle",
      Running: "Running",
      Done: "Done",
      Canceled: "Canceled",
      Error: "Error",
      Unavailable: "Unavailable",
      "Runtime Error": "Runtime Error",
      "No Files": "No Files",
      "Needs Input": "Needs Input",
    },
    queueStatus: {
      queued: "queued",
      inspecting: "inspecting",
      ready: "ready",
      running: "running",
      done: "done",
      error: "error",
    },
    badges: {
      inspectError: "Inspect error",
      gainmap: "Gainmap",
      sdr: "SDR",
      inspecting: "Inspecting",
      pending: "Pending",
    },
    infoLabels: {
      file: "File",
      format: "Format",
      dimensions: "Dimensions",
      fileSize: "File Size",
      color: "Color",
      colorSource: "Color Source",
      cicp: "CICP/nclx",
      hdr: "HDR",
      rgbPeak: "RGB Peak",
      headroom: "Headroom",
      gainMap: "Gain Map",
      baseHeadroom: "Base Headroom",
      altHeadroom: "Alt Headroom",
      error: "Error",
      warning: "Warning",
      output: "Output",
      peak: "Peak",
      verify: "Verify",
    },
    help: {
      format: {
        title: "Output Format",
        body: "Choose the container and HDR delivery model. JPEG XL Linear is the safest archive master. AVIF/HEIF are standard PQ display files. Ultra HDR and Gainmap AVIF are compatibility formats with SDR fallback behavior.",
      },
      fidelity: {
        title: "Fidelity",
        body: "Master keeps a reprocessing-friendly linear HDR file. Display HDR creates viewable PQ output. Compat creates gain-map based output for readers that need an SDR base.",
      },
      "jxl-mode": {
        title: "JPEG XL HDR Mode",
        body: "Linear Archive stores scRGB-like linear HDR and is best for masters. Rec.2020 PQ is better for display and sharing, but it is not the strict archive path.",
      },
      lossless: {
        title: "Lossless JPEG XL",
        body: "For Linear Archive, lossless keeps the strict master behavior. For display-oriented conversions, lossless only applies after the HDR transfer/color conversion step.",
      },
      "uhdr-backend": {
        title: "Ultra HDR Backend",
        body: "Auto prefers libultrahdr when available and falls back to imagecodecs. libultrahdr is required for the dedicated known PQ TIFF path. imagecodecs is the legacy fallback.",
      },
      "uhdr-gainmap-scale": {
        title: "Gainmap Scale",
        body: "Controls Ultra HDR gain map resolution. Lower values keep more detail and larger files. 2 is the recommended compatibility default.",
      },
      "target-peak": {
        title: "Target Peak Nits",
        body: "Sets the target HDR display peak for libultrahdr encoding. 1000 nits is the default for the known PQ TIFF workflow.",
      },
      "pq-tiff": {
        title: "Known BT.2020 PQ TIFF",
        body: "Use only when the TIFF RGB samples are known to be BT.2020 primaries with PQ/ST.2084 transfer. Do not enable it for ordinary TIFF files.",
      },
      "gainmap-headroom-mode": {
        title: "Gainmap Headroom Mode",
        body: "Source Peak writes Alternate headroom from the decoded HDR peak and is the fidelity path. Auto keeps libavif's computed metadata.",
      },
      "base-headroom": {
        title: "Base Headroom",
        body: "Controls how much highlight detail is preserved in SDR base tone mapping for gain-map outputs. Higher values can reduce SDR contrast but preserve more highlight structure.",
      },
      quality: {
        title: "Quality",
        body: "Higher values preserve more detail and usually increase file size. Use 100 for fidelity testing and compatibility debugging.",
      },
      speed: {
        title: "Speed",
        body: "Encoder effort. 0 is slowest with best compression efficiency; 10 is fastest. This does not replace the quality setting.",
      },
      "debug-overlay": {
        title: "Debug Info Overlay",
        body: "Writes an SDR PNG sidecar with diagnostic text. The converted output image is not modified.",
      },
      "info-json": {
        title: "Output Info JSON",
        body: "Writes a sidecar JSON with format, CICP, gain map, peak, verification, and inspector metadata. Keep this on when debugging HDR compatibility.",
      },
      "verify-fidelity": {
        title: "Verify Fidelity",
        body: "Runs post-encode checks and fails the conversion if metadata or reconstructed peak falls outside project thresholds.",
      },
      "output-naming": {
        title: "Output Naming Pattern",
        body: "Use {name} for the original filename and {n} for sequence numbering. Prefix, suffix, find, and replace are applied before writing output files.",
      },
    },
    messages: {
      helpDefault: "Select an option help button to see guidance.",
      noImagesSelected: "No images selected.",
      queuedCount: "{count} image{plural} queued.",
      noImageInfo: "No image information available.",
      inspecting: "Inspecting selected image metadata...",
      selectImage: "Select a queued image to inspect technical metadata.",
      metadataNotLoaded: "Metadata not loaded yet.",
      reportEmpty: "Conversion reports will appear here when Info JSON is enabled.",
      noLogs: "No log entries.",
      logSummary: "{total} entries, {warnings} warnings, {errors} errors.",
      runningProgress: "Running {current}/{total}",
      runtimeCheckFailed: "Runtime check failed.",
      runtimeReady: "Runtime ready. Python {version}; bundled tools found; {uhdrText}.",
      uhdrAvailable: "libultrahdr available",
      uhdrMissing: "libultrahdr optional DLL not found",
      runtimeError: "Runtime error: {issue}",
      runtimeSelfCheckFailed: "Runtime self-check failed: {issue}",
      checkingRuntime: "Checking runtime...",
      selectAtLeastOne: "Select at least one image file first.",
      selectInputFirst: "Select an input file or folder first.",
      qualityRange: "Quality must be between 0 and 100.",
      speedRange: "Speed must be between 0 and 10.",
      headroomPositive: "Base headroom must be greater than 0.",
      gainmapScaleRange: "Ultra HDR gainmap scale must be between 1 and 128.",
      targetPeakRange: "Ultra HDR target peak must be between 203 and 10000 nits.",
      unknownUhdrBackend: "Unknown Ultra HDR backend.",
      unknownJxlMode: "Unknown JPEG XL mode.",
      unknownFidelity: "Unknown fidelity mode.",
      unknownGainmapHeadroom: "Unknown gainmap headroom mode.",
      nameStartRange: "Name start must be 0 or higher.",
      namePaddingRange: "Name padding must be 0 or higher.",
      pqTiffWarning: "BT.2020 PQ TIFF mode assumes untagged TIFF RGB samples are true BT.2020 PQ/ST.2084. Keep it off for ordinary TIFF files.",
      uhdrAutoWarning: "libultrahdr is not available. Auto will fall back to the legacy imagecodecs Ultra HDR path.",
      uhdrLibWarning: "libultrahdr is not available. This conversion will fail until HDR_TRANSCODER_UHDR_DLL or tools/libultrahdr/uhdr.dll is configured.",
      outputFolderSelected: "Output folder selected.",
      defaultOutputUsed: "Default output location will be used.",
      queueCleared: "Queue cleared.",
      oneImageSelected: "1 image selected.",
      imagesSelected: "{count} images selected.",
      noSupportedFiles: "No supported image files found in this folder.",
      folderSelected: "Folder selected. Found {count} supported image(s).",
      conversionStarted: "Conversion started",
      conversionRunning: "Conversion running.",
      conversionCanceled: "Conversion canceled.",
      cancelRequested: "Cancel requested.",
      conversionFailed: "Conversion failed.",
      conversionEnded: "Conversion ended.",
      finished: "Finished.",
      finishedChecked: "Finished. {count} output path(s) checked.",
      overwriteExtra: " and {count} more",
      overwriteConfirm: "{count} output file(s) already exist:\n\n{names}{extra}\n\nOverwrite?",
      infoReadFailed: "Unable to read output info JSON: {message}",
      preloadUnavailable: "Electron preload API is unavailable. Start this UI with npm start.",
    },
  },
};

const state = {
  language: DEFAULT_LANGUAGE,
  inputPath: "",
  inputPaths: [],
  inputMode: "files",
  outputDir: "",
  selectedFileId: "",
  queueItems: [],
  activeHelpTopic: "",
  advancedOpen: false,
  logFilter: "all",
  logs: [],
  running: false,
  runtimeOk: true,
  runtimeInfo: null,
  uhdrAvailable: false,
  inspectRequestId: 0,
  outputReports: [],
  statusLabel: "Idle",
  statusClassName: "idle",
  statusProgress: null,
};

const elements = {
  form: document.getElementById("convertForm"),
  pickFilesButton: document.getElementById("pickFilesButton"),
  pickDirectoryButton: document.getElementById("pickDirectoryButton"),
  pickOutputButton: document.getElementById("pickOutputButton"),
  runtimeCheckButton: document.getElementById("runtimeCheckButton"),
  clearQueueButton: document.getElementById("clearQueueButton"),
  startButton: document.getElementById("startButton"),
  cancelButton: document.getElementById("cancelButton"),
  clearLogButton: document.getElementById("clearLogButton"),
  logToggleButton: document.getElementById("logToggleButton"),
  languageSelect: document.getElementById("languageSelect"),
  inputPath: null,
  outputPath: document.getElementById("outputPath"),
  clearOutputButton: document.getElementById("clearOutputButton"),
  queueList: document.getElementById("queueList"),
  queueSummary: document.getElementById("queueSummary"),
  queueEmpty: document.getElementById("queueEmpty"),
  formatSelect: document.getElementById("formatSelect"),
  fidelityBadge: document.getElementById("fidelityBadge"),
  jxlOptions: document.getElementById("jxlOptions"),
  ultrahdrOptions: document.getElementById("ultrahdrOptions"),
  gainmapOptions: document.getElementById("gainmapOptions"),
  displayHdrOptions: document.getElementById("displayHdrOptions"),
  headroomOptions: document.getElementById("headroomOptions"),
  jxlModeSelect: document.getElementById("jxlModeSelect"),
  qualityInput: document.getElementById("qualityInput"),
  speedInput: document.getElementById("speedInput"),
  gainmapHeadroomModeSelect: document.getElementById("gainmapHeadroomModeSelect"),
  headroomSdrInput: document.getElementById("headroomSdrInput"),
  uhdrBackendSelect: document.getElementById("uhdrBackendSelect"),
  uhdrGainmapScaleInput: document.getElementById("uhdrGainmapScaleInput"),
  uhdrTargetPeakInput: document.getElementById("uhdrTargetPeakInput"),
  bt2020PqTiffInput: document.getElementById("bt2020PqTiffInput"),
  losslessInput: document.getElementById("losslessInput"),
  verifyFidelityInput: document.getElementById("verifyFidelityInput"),
  debugOverlayInput: document.getElementById("debugOverlayInput"),
  infoJsonInput: document.getElementById("infoJsonInput"),
  advancedPanel: document.getElementById("advancedPanel"),
  namePrefixInput: document.getElementById("namePrefixInput"),
  nameSuffixInput: document.getElementById("nameSuffixInput"),
  nameFindInput: document.getElementById("nameFindInput"),
  nameReplaceInput: document.getElementById("nameReplaceInput"),
  namePatternInput: document.getElementById("namePatternInput"),
  nameStartInput: document.getElementById("nameStartInput"),
  namePaddingInput: document.getElementById("namePaddingInput"),
  settingsWarning: document.getElementById("settingsWarning"),
  helpContent: document.getElementById("helpContent"),
  imageInfoContent: document.getElementById("imageInfoContent"),
  outputReportContent: document.getElementById("outputReportContent"),
  runtimeStatus: document.getElementById("runtimeStatus"),
  statusBadge: document.getElementById("statusBadge"),
  summary: document.getElementById("summary"),
  logDrawer: document.getElementById("logDrawer"),
  logOutput: document.getElementById("logOutput"),
  logSummary: document.getElementById("logSummary"),
};

function currentDictionary() {
  return I18N[state.language] || I18N[DEFAULT_LANGUAGE];
}

function lookupText(source, key) {
  return String(key || "").split(".").reduce((value, part) => {
    if (value && Object.prototype.hasOwnProperty.call(value, part)) {
      return value[part];
    }
    return undefined;
  }, source);
}

function interpolate(text, params = {}) {
  return String(text).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name) => (
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match
  ));
}

function t(key, params = {}) {
  const value = lookupText(currentDictionary(), key) ?? lookupText(I18N.en, key) ?? key;
  return interpolate(value, params);
}

function translatedValue(group, key) {
  return lookupText(currentDictionary(), `${group}.${key}`) ?? lookupText(I18N.en, `${group}.${key}`) ?? key;
}

function translateStatus(label) {
  return lookupText(currentDictionary(), `status.${label}`) ?? lookupText(I18N.en, `status.${label}`) ?? label;
}

function translateQueueStatus(status) {
  return lookupText(currentDictionary(), `queueStatus.${status}`) ?? lookupText(I18N.en, `queueStatus.${status}`) ?? status;
}

function setStaticText() {
  document.documentElement.lang = state.language;
  document.title = t("documentTitle");

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  });

  if (elements.languageSelect) {
    elements.languageSelect.value = state.language;
  }
}

function renderStatusBadge() {
  if (state.statusProgress) {
    elements.statusBadge.textContent = t("messages.runningProgress", state.statusProgress);
  } else {
    elements.statusBadge.textContent = translateStatus(state.statusLabel);
  }
  elements.statusBadge.className = `status-badge ${state.statusClassName}`;
}

function setLanguage(language, rerender = true) {
  state.language = I18N[language] ? language : DEFAULT_LANGUAGE;
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
  } catch {
    // Local storage can be unavailable in test harnesses.
  }

  setStaticText();
  if (!rerender) {
    return;
  }
  renderStatusBadge();
  renderHelp(state.activeHelpTopic);
  renderQueue();
  renderInspector();
  renderOutputReports();
  renderLog();
  updateFormatState();
  setPathDisplay(elements.outputPath, state.outputDir, t("ui.defaultOutputLocation"));
  elements.logToggleButton.textContent = elements.logDrawer.classList.contains("collapsed") ? t("ui.expand") : t("ui.collapse");
  if (state.runtimeInfo) {
    renderRuntimeStatus(state.runtimeInfo, { quiet: true });
  }
}

function initializeLanguage() {
  let savedLanguage = DEFAULT_LANGUAGE;
  try {
    savedLanguage = localStorage.getItem(LANGUAGE_STORAGE_KEY) || DEFAULT_LANGUAGE;
  } catch {
    savedLanguage = DEFAULT_LANGUAGE;
  }
  setLanguage(savedLanguage, false);
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function basename(filePath) {
  const parts = String(filePath).split(/[/\\]/);
  return parts[parts.length - 1] || String(filePath);
}

function normalizePath(filePath) {
  return String(filePath || "").replaceAll("\\", "/").toLowerCase();
}

function formatBytes(bytes) {
  if (typeof bytes !== "number") {
    return t("unknown");
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatFloat(value, digits = 3) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : t("unknown");
}

function setStatus(label, className) {
  state.statusLabel = label;
  state.statusClassName = className;
  state.statusProgress = null;
  renderStatusBadge();
}

function setSummary(text) {
  elements.summary.textContent = text;
}

function setPathDisplay(node, value, emptyText) {
  node.textContent = value || emptyText;
  node.classList.toggle("empty", !value);
}

function setImageInfoMessage(text, className = "empty") {
  clearNode(elements.imageInfoContent);
  elements.imageInfoContent.textContent = text;
  elements.imageInfoContent.className = `image-info-content ${className}`.trim();
}

function addInfoRow(container, label, value, className = "") {
  const row = document.createElement("div");
  row.className = `info-row ${className}`.trim();

  const labelNode = document.createElement("span");
  labelNode.className = "info-label";
  labelNode.textContent = label;

  const valueNode = document.createElement("span");
  valueNode.className = "info-value";
  valueNode.textContent = value == null || value === "" ? t("unknown") : String(value);

  row.appendChild(labelNode);
  row.appendChild(valueNode);
  container.appendChild(row);
}

function createBadge(text, className = "") {
  const badge = document.createElement("span");
  badge.className = `mini-badge ${className}`.trim();
  badge.textContent = text;
  return badge;
}

function renderHelp(topicKey) {
  clearNode(elements.helpContent);
  const topic = lookupText(currentDictionary(), `help.${topicKey}`) ?? lookupText(I18N.en, `help.${topicKey}`);
  if (!topic) {
    elements.helpContent.textContent = t("messages.helpDefault");
    elements.helpContent.className = "help-content empty";
    return;
  }

  elements.helpContent.className = "help-content";
  const title = document.createElement("div");
  title.className = "help-title";
  title.textContent = topic.title;
  const body = document.createElement("div");
  body.className = "help-body";
  body.textContent = topic.body;
  elements.helpContent.appendChild(title);
  elements.helpContent.appendChild(body);
}

function queueItemMeta(item) {
  const info = item.info || {};
  const badges = [];
  if (info.error) {
    badges.push(createBadge(t("badges.inspectError"), "error"));
    return badges;
  }

  if (info.detected_format || info.format_name) {
    badges.push(createBadge(info.detected_format || info.format_name));
  }
  if (info.width && info.height) {
    badges.push(createBadge(`${info.width}x${info.height}`));
  }
  if (info.hdr && info.hdr.is_hdr) {
    badges.push(createBadge(`HDR ${formatFloat(info.hdr.rgb_max, 2)}`, "hdr"));
  } else if (info.hdr) {
    badges.push(createBadge(t("badges.sdr")));
  }
  if (info.gainmap && info.gainmap.present) {
    badges.push(createBadge(t("badges.gainmap"), "gainmap"));
  }
  if (badges.length === 0) {
    badges.push(createBadge(item.status === "inspecting" ? t("badges.inspecting") : t("badges.pending")));
  }
  return badges;
}

function renderQueue() {
  clearNode(elements.queueList);
  const count = state.queueItems.length;
  elements.queueSummary.textContent = count === 0
    ? t("messages.noImagesSelected")
    : t("messages.queuedCount", { count, plural: count === 1 ? "" : "s" });

  for (const item of state.queueItems) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `queue-item ${item.id === state.selectedFileId ? "selected" : ""}`;
    button.addEventListener("click", () => selectQueueItem(item.id));

    const name = document.createElement("span");
    name.className = "queue-name";
    name.textContent = item.name;
    button.appendChild(name);

    const path = document.createElement("span");
    path.className = "queue-path";
    path.textContent = item.path;
    button.appendChild(path);

    const meta = document.createElement("div");
    meta.className = "queue-meta";
    for (const badge of queueItemMeta(item)) {
      meta.appendChild(badge);
    }
    const status = document.createElement("span");
    status.className = `queue-status ${item.status || "queued"}`;
    status.textContent = translateQueueStatus(item.status || "queued");
    meta.appendChild(status);
    button.appendChild(meta);

    elements.queueList.appendChild(button);
  }
}

function setQueueItems(paths, inputMode, inputPath = "") {
  state.inputMode = inputMode;
  state.inputPath = inputPath;
  state.inputPaths = inputMode === "files" ? paths : [];
  state.queueItems = paths.map((filePath, index) => ({
    id: `file-${Date.now()}-${index}`,
    path: filePath,
    name: basename(filePath),
    status: "queued",
    info: null,
  }));
  state.selectedFileId = state.queueItems.length > 0 ? state.queueItems[0].id : "";
  state.outputReports = [];
  renderQueue();
  renderInspector();
  renderOutputReports();
}

function selectedQueueItem() {
  return state.queueItems.find((item) => item.id === state.selectedFileId) || null;
}

function selectQueueItem(id) {
  state.selectedFileId = id;
  renderQueue();
  const item = selectedQueueItem();
  if (item && !item.info) {
    loadImageInfo([item.path]);
  } else {
    renderInspector();
  }
}

function mergeImageInfos(payload) {
  const infos = Array.isArray(payload) ? payload : [payload];
  const byPath = new Map();
  for (const info of infos) {
    byPath.set(normalizePath(info.path), info);
  }

  state.queueItems = state.queueItems.map((item) => {
    const info = byPath.get(normalizePath(item.path));
    if (!info) {
      return item;
    }
    return { ...item, info, status: info.error ? "error" : "ready" };
  });
  renderQueue();
  renderInspector();
}

async function loadImageInfo(filePaths) {
  if (!filePaths || filePaths.length === 0) {
    setImageInfoMessage(t("messages.noImageInfo"));
    return;
  }

  const requestId = ++state.inspectRequestId;
  state.queueItems = state.queueItems.map((item) => (
    filePaths.includes(item.path) && !item.info ? { ...item, status: "inspecting" } : item
  ));
  renderQueue();
  setImageInfoMessage(t("messages.inspecting"), "loading");

  try {
    const result = await window.hdrTranscoder.inspectImages(filePaths);
    if (requestId !== state.inspectRequestId) {
      return;
    }
    mergeImageInfos(result);
  } catch (error) {
    if (requestId !== state.inspectRequestId) {
      return;
    }
    setImageInfoMessage(error && error.message ? error.message : String(error), "error");
    state.queueItems = state.queueItems.map((item) => (
      filePaths.includes(item.path) ? { ...item, status: "error" } : item
    ));
    renderQueue();
  }
}

function renderInspector() {
  const item = selectedQueueItem();
  if (!item) {
    setImageInfoMessage(t("messages.selectImage"));
    return;
  }
  if (!item.info) {
    setImageInfoMessage(
      item.status === "inspecting" ? t("messages.inspecting") : t("messages.metadataNotLoaded"),
      item.status === "inspecting" ? "loading" : "empty",
    );
    return;
  }

  const info = item.info;
  clearNode(elements.imageInfoContent);
  elements.imageInfoContent.className = "image-info-content";

  addInfoRow(elements.imageInfoContent, t("infoLabels.file"), info.filename || item.name);
  addInfoRow(elements.imageInfoContent, t("infoLabels.format"), `${info.format_name || t("unknown")} (${info.detected_format || t("unknown")})`);
  addInfoRow(elements.imageInfoContent, t("infoLabels.dimensions"), info.width && info.height ? `${info.width} x ${info.height}` : t("unknown"));
  addInfoRow(elements.imageInfoContent, t("infoLabels.fileSize"), formatBytes(info.file_size_bytes));

  const color = info.color || {};
  addInfoRow(
    elements.imageInfoContent,
    t("infoLabels.color"),
    `${color.primaries_label || t("unknown")} / ${color.transfer_label || t("unknown")} / ${color.matrix_label || t("unknown")}`,
  );
  if (color.source) {
    addInfoRow(elements.imageInfoContent, t("infoLabels.colorSource"), color.source);
  }
  if (color.primaries || color.transfer || color.matrix) {
    addInfoRow(elements.imageInfoContent, t("infoLabels.cicp"), `${color.primaries || "?"}/${color.transfer || "?"}/${color.matrix || "?"}`);
  }

  const hdr = info.hdr || {};
  addInfoRow(elements.imageInfoContent, t("infoLabels.hdr"), hdr.is_hdr ? t("yes") : t("no"));
  addInfoRow(elements.imageInfoContent, t("infoLabels.rgbPeak"), `${formatFloat(hdr.rgb_max)} scRGB`);
  addInfoRow(elements.imageInfoContent, t("infoLabels.headroom"), `${formatFloat(hdr.peak_headroom)} stops`);

  const gainmap = info.gainmap || {};
  addInfoRow(elements.imageInfoContent, t("infoLabels.gainMap"), gainmap.present ? t("present") : t("notDetected"));
  if (gainmap.present) {
    addInfoRow(elements.imageInfoContent, t("infoLabels.baseHeadroom"), `${formatFloat(gainmap.base_headroom ?? gainmap.baseHeadroom)} stops`);
    addInfoRow(elements.imageInfoContent, t("infoLabels.altHeadroom"), `${formatFloat(gainmap.alternate_headroom ?? gainmap.alternateHeadroom)} stops`);
  }

  if (info.error) {
    addInfoRow(elements.imageInfoContent, t("infoLabels.error"), info.error, "error");
  }
  for (const warning of info.warnings || []) {
    addInfoRow(elements.imageInfoContent, t("infoLabels.warning"), warning, "warning");
  }
}

function renderOutputReports() {
  clearNode(elements.outputReportContent);
  if (state.outputReports.length === 0) {
    elements.outputReportContent.className = "output-report-content empty";
    elements.outputReportContent.textContent = t("messages.reportEmpty");
    return;
  }

  elements.outputReportContent.className = "output-report-content";
  for (const report of state.outputReports) {
    const card = document.createElement("div");
    card.className = "report-card";
    addInfoRow(card, t("infoLabels.output"), report.path || t("unknown"));
    addInfoRow(card, t("infoLabels.format"), report.format || t("unknown"));
    if (report.peak) {
      addInfoRow(card, t("infoLabels.peak"), `${formatFloat(report.peak.rgbMax)} scRGB`);
      addInfoRow(card, t("infoLabels.headroom"), `${formatFloat(report.peak.headroom)} stops`);
    }
    if (report.verify) {
      addInfoRow(card, t("infoLabels.verify"), report.verify.ok ? t("passed") : t("failed"), report.verify.ok ? "" : "error");
    }
    const gainmap = report.gainmap || {};
    if (gainmap.present != null) {
      addInfoRow(card, t("infoLabels.gainMap"), gainmap.present ? t("present") : t("notDetected"));
    }
    elements.outputReportContent.appendChild(card);
  }
}

function classifyLog(text, stream) {
  if (stream === "stderr" || /error|failed|traceback/i.test(text)) {
    return "error";
  }
  if (/warning|warn|fallback|missing/i.test(text)) {
    return "warning";
  }
  return "info";
}

function renderLog() {
  const filtered = state.logs.filter((entry) => state.logFilter === "all" || entry.level === state.logFilter);
  elements.logOutput.textContent = filtered.map((entry) => entry.text).join("");
  const warnings = state.logs.filter((entry) => entry.level === "warning").length;
  const errors = state.logs.filter((entry) => entry.level === "error").length;
  elements.logSummary.textContent = state.logs.length === 0
    ? t("messages.noLogs")
    : t("messages.logSummary", { total: state.logs.length, warnings, errors });
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
}

function appendLog(text, stream = "stdout") {
  if (!text) {
    return;
  }
  const prefix = stream === "stderr" ? "[stderr] " : stream === "system" ? "[cmd] " : "";
  const level = classifyLog(text, stream);
  state.logs.push({ text: `${prefix}${text}`, stream, level });
  renderLog();

  const progressMatch = text.match(/\[(\d+)\/(\d+)\]/);
  if (progressMatch) {
    const current = Number(progressMatch[1]);
    const total = Number(progressMatch[2]);
    state.statusClassName = "running";
    state.statusProgress = { current, total };
    renderStatusBadge();
    state.queueItems = state.queueItems.map((item, index) => {
      if (index + 1 < current) {
        return { ...item, status: "done" };
      }
      if (index + 1 === current) {
        return { ...item, status: "running" };
      }
      return item;
    });
    renderQueue();
  }
}

function formatRuntimeIssue(result) {
  const missing = (result.missingTools || []).map((tool) => tool.name || tool.path);
  const deps = (result.dependencyErrors || []).map((item) => item.package || item.module || item.error);
  const issues = [...missing, ...deps];
  return issues.length > 0 ? issues.join(", ") : t("messages.runtimeCheckFailed");
}

function updateUhdrAvailability(result) {
  const optional = result && result.optionalTools ? result.optionalTools["uhdr.dll"] : null;
  state.uhdrAvailable = !!(optional && optional.present);
}

function renderRuntimeStatus(result, options = {}) {
  state.runtimeInfo = result || null;
  state.runtimeOk = !!(result && result.ok);
  updateUhdrAvailability(result);
  if (state.runtimeOk) {
    const version = result.pythonVersion && result.pythonVersion.version ? result.pythonVersion.version : t("unknown");
    const uhdrText = state.uhdrAvailable ? t("messages.uhdrAvailable") : t("messages.uhdrMissing");
    elements.runtimeStatus.textContent = t("messages.runtimeReady", { version, uhdrText });
    elements.runtimeStatus.className = "runtime-status ok";
    if (!state.running) {
      setStatus("Idle", "idle");
    }
  } else {
    const issue = formatRuntimeIssue(result || {});
    elements.runtimeStatus.textContent = t("messages.runtimeError", { issue });
    elements.runtimeStatus.className = "runtime-status error";
    setStatus("Runtime Error", "error");
    setSummary(t("messages.runtimeSelfCheckFailed", { issue }));
    if (!options.quiet) {
      appendLog(`${t("messages.runtimeSelfCheckFailed", { issue })}\n`, "stderr");
    }
  }
  updateBusyState(state.running);
  updateFormatState();
}

function getNumberValue(input, fallback) {
  const value = Number(input.value);
  return Number.isFinite(value) ? value : fallback;
}

function getFidelityMode() {
  if (
    elements.formatSelect.value === "jxl" &&
    elements.jxlModeSelect.value === "linear-srgb" &&
    elements.losslessInput.checked
  ) {
    return "master";
  }
  if (["jxl", "avif", "heif"].includes(elements.formatSelect.value)) {
    return "display";
  }
  return "compat";
}

function getOptions() {
  return {
    inputPath: state.inputPath,
    inputPaths: state.inputPaths,
    inputMode: state.inputMode,
    outputDir: state.outputDir,
    format: elements.formatSelect.value,
    fidelity: getFidelityMode(),
    jxlMode: elements.jxlModeSelect.value,
    quality: Math.trunc(getNumberValue(elements.qualityInput, 100)),
    speed: Math.trunc(getNumberValue(elements.speedInput, 0)),
    gainmapHeadroomMode: elements.gainmapHeadroomModeSelect.value,
    headroom: getNumberValue(elements.headroomSdrInput, 2.0),
    lossless: elements.losslessInput.checked,
    verifyFidelity: elements.verifyFidelityInput.checked,
    debugOverlay: elements.debugOverlayInput.checked,
    infoJson: elements.infoJsonInput.checked,
    bt2020PqTiff: elements.bt2020PqTiffInput.checked,
    uhdrBackend: elements.uhdrBackendSelect.value,
    uhdrGainmapScale: Math.trunc(getNumberValue(elements.uhdrGainmapScaleInput, 2)),
    uhdrTargetPeakNits: getNumberValue(elements.uhdrTargetPeakInput, 1000),
    namePrefix: elements.namePrefixInput.value,
    nameSuffix: elements.nameSuffixInput.value,
    nameFind: elements.nameFindInput.value,
    nameReplace: elements.nameReplaceInput.value,
    namePattern: elements.namePatternInput.value || "{name}",
    nameStart: Math.trunc(getNumberValue(elements.nameStartInput, 1)),
    namePadding: Math.trunc(getNumberValue(elements.namePaddingInput, 3)),
  };
}

function validateOptions(options) {
  if (options.inputMode === "files") {
    if (!Array.isArray(options.inputPaths) || options.inputPaths.length === 0) {
      return t("messages.selectAtLeastOne");
    }
  } else if (!options.inputPath) {
    return t("messages.selectInputFirst");
  }
  if (options.quality < 0 || options.quality > 100) {
    return t("messages.qualityRange");
  }
  if (options.speed < 0 || options.speed > 10) {
    return t("messages.speedRange");
  }
  if (options.headroom <= 0) {
    return t("messages.headroomPositive");
  }
  if (options.uhdrGainmapScale < 1 || options.uhdrGainmapScale > 128) {
    return t("messages.gainmapScaleRange");
  }
  if (options.uhdrTargetPeakNits < 203 || options.uhdrTargetPeakNits > 10000) {
    return t("messages.targetPeakRange");
  }
  if (!["auto", "imagecodecs", "libultrahdr"].includes(options.uhdrBackend)) {
    return t("messages.unknownUhdrBackend");
  }
  if (!["rec2020-pq", "linear-srgb"].includes(options.jxlMode)) {
    return t("messages.unknownJxlMode");
  }
  if (!["master", "display", "compat"].includes(options.fidelity)) {
    return t("messages.unknownFidelity");
  }
  if (!["source-peak", "auto"].includes(options.gainmapHeadroomMode)) {
    return t("messages.unknownGainmapHeadroom");
  }
  if (options.nameStart < 0) {
    return t("messages.nameStartRange");
  }
  if (options.namePadding < 0) {
    return t("messages.namePaddingRange");
  }
  return "";
}

function renderSettingsWarning() {
  const warnings = [];
  const isUltraHdr = elements.formatSelect.value === "ultrahdr";
  const pqTiff = elements.bt2020PqTiffInput.checked;
  const backend = elements.uhdrBackendSelect.value;

  if (pqTiff) {
    warnings.push(t("messages.pqTiffWarning"));
  }
  if (isUltraHdr && pqTiff && state.runtimeInfo && !state.uhdrAvailable && backend === "auto") {
    warnings.push(t("messages.uhdrAutoWarning"));
  }
  if (isUltraHdr && pqTiff && state.runtimeInfo && !state.uhdrAvailable && backend === "libultrahdr") {
    warnings.push(t("messages.uhdrLibWarning"));
  }

  if (warnings.length === 0) {
    elements.settingsWarning.hidden = true;
    elements.settingsWarning.textContent = "";
  } else {
    elements.settingsWarning.hidden = false;
    elements.settingsWarning.textContent = warnings.join(" ");
  }
}

function updateFormatState() {
  const format = elements.formatSelect.value;
  const isJxl = format === "jxl";
  const isUltraHdr = format === "ultrahdr";
  const isGainmap = format === "gainmap";
  const isDisplayHdr = format === "avif" || format === "heif";

  elements.jxlOptions.hidden = !isJxl;
  elements.ultrahdrOptions.hidden = !isUltraHdr;
  elements.gainmapOptions.hidden = !isGainmap;
  elements.displayHdrOptions.hidden = !isDisplayHdr;
  elements.headroomOptions.hidden = !(isGainmap || isUltraHdr);

  elements.losslessInput.disabled = !isJxl || state.running;
  elements.jxlModeSelect.disabled = !isJxl || state.running;
  elements.gainmapHeadroomModeSelect.disabled = !isGainmap || state.running;
  elements.uhdrBackendSelect.disabled = !isUltraHdr || state.running;
  elements.uhdrGainmapScaleInput.disabled = !isUltraHdr || state.running;
  elements.uhdrTargetPeakInput.disabled = !isUltraHdr || state.running;
  elements.bt2020PqTiffInput.disabled = !isUltraHdr || state.running;
  elements.headroomSdrInput.disabled = !(isGainmap || isUltraHdr) || state.running;

  if (!isJxl) {
    elements.losslessInput.checked = false;
  }

  const fidelity = getFidelityMode();
  elements.fidelityBadge.textContent =
    translatedValue("fidelity", fidelity);
  elements.fidelityBadge.className = `fidelity-badge ${fidelity}`;
  renderSettingsWarning();
}

function updateBusyState(running) {
  state.running = running;
  const disabled = running;
  elements.pickFilesButton.disabled = disabled;
  elements.pickDirectoryButton.disabled = disabled;
  elements.pickOutputButton.disabled = disabled;
  elements.runtimeCheckButton.disabled = disabled;
  elements.clearQueueButton.disabled = disabled;
  elements.clearOutputButton.disabled = disabled;
  elements.startButton.disabled = disabled || !state.runtimeOk;
  elements.cancelButton.disabled = !disabled;
  elements.formatSelect.disabled = disabled;
  elements.qualityInput.disabled = disabled;
  elements.speedInput.disabled = disabled;
  elements.verifyFidelityInput.disabled = disabled;
  elements.debugOverlayInput.disabled = disabled;
  elements.infoJsonInput.disabled = disabled;
  elements.namePrefixInput.disabled = disabled;
  elements.nameSuffixInput.disabled = disabled;
  elements.nameFindInput.disabled = disabled;
  elements.nameReplaceInput.disabled = disabled;
  elements.namePatternInput.disabled = disabled;
  elements.nameStartInput.disabled = disabled;
  elements.namePaddingInput.disabled = disabled;
  updateFormatState();
}

async function chooseInputFiles() {
  const filePaths = await window.hdrTranscoder.selectInputFiles();
  if (!filePaths || filePaths.length === 0) {
    return;
  }

  setQueueItems(filePaths, "files");
  setSummary(filePaths.length === 1 ? t("messages.oneImageSelected") : t("messages.imagesSelected", { count: filePaths.length }));
  loadImageInfo(filePaths);
}

async function chooseInputDirectory() {
  const directoryPath = await window.hdrTranscoder.selectInputDirectory();
  if (!directoryPath) {
    return;
  }

  const scan = await window.hdrTranscoder.scanDirectory(directoryPath);
  const files = Array.isArray(scan.files)
    ? scan.files.map((item) => (typeof item === "string" ? item : item.path)).filter(Boolean)
    : [];
  setQueueItems(files, "directory", directoryPath);
  if (scan.error) {
    setSummary(scan.error);
    setStatus("No Files", "error");
  } else if (files.length === 0) {
    setSummary(t("messages.noSupportedFiles"));
    setStatus("No Files", "error");
  } else {
    setSummary(t("messages.folderSelected", { count: files.length }));
    loadImageInfo(files);
  }
}

async function chooseOutputDirectory() {
  const directoryPath = await window.hdrTranscoder.selectOutputDirectory();
  if (!directoryPath) {
    return;
  }

  state.outputDir = directoryPath;
  setPathDisplay(elements.outputPath, directoryPath, t("ui.defaultOutputLocation"));
  setSummary(t("messages.outputFolderSelected"));
}

function clearOutputDirectory() {
  state.outputDir = "";
  setPathDisplay(elements.outputPath, "", t("ui.defaultOutputLocation"));
  setSummary(t("messages.defaultOutputUsed"));
}

function clearQueue() {
  state.inputPath = "";
  state.inputPaths = [];
  state.inputMode = "files";
  state.queueItems = [];
  state.selectedFileId = "";
  state.outputReports = [];
  renderQueue();
  renderInspector();
  renderOutputReports();
  setSummary(t("messages.queueCleared"));
}

function setQueueRunning() {
  state.queueItems = state.queueItems.map((item, index) => ({
    ...item,
    status: index === 0 ? "running" : "queued",
  }));
  renderQueue();
}

function setQueueFinished(ok) {
  state.queueItems = state.queueItems.map((item) => ({
    ...item,
    status: ok ? "done" : item.status === "done" ? "done" : "error",
  }));
  renderQueue();
}

async function startConversion(event) {
  event.preventDefault();

  const options = getOptions();
  const validationError = validateOptions(options);
  if (validationError) {
    setStatus("Needs Input", "error");
    setSummary(validationError);
    return;
  }

  const overwrite = await window.hdrTranscoder.checkOverwrite(options);
  if (overwrite.existing && overwrite.existing.length > 0) {
    const names = overwrite.existing.map((p) => p.split(/[/\\]/).pop()).slice(0, 5).join(", ");
    const extra = overwrite.existing.length > 5 ? t("messages.overwriteExtra", { count: overwrite.existing.length - 5 }) : "";
    const confirmed = confirm(
      t("messages.overwriteConfirm", { count: overwrite.existing.length, names, extra }),
    );
    if (!confirmed) {
      setSummary(t("messages.conversionCanceled"));
      return;
    }
  }

  updateBusyState(true);
  setQueueRunning();
  setStatus("Running", "running");
  setSummary(t("messages.conversionRunning"));
  state.outputReports = [];
  renderOutputReports();
  appendLog(`\n--- ${t("messages.conversionStarted")} ---\n`, "system");

  try {
    await window.hdrTranscoder.startConversion(options);
  } catch (error) {
    updateBusyState(false);
    setQueueFinished(false);
    setStatus("Error", "error");
    setSummary(error && error.message ? error.message : String(error));
  }
}

async function cancelConversion() {
  if (!state.running) {
    return;
  }

  setSummary(t("messages.cancelRequested"));
  await window.hdrTranscoder.cancelConversion();
}

async function loadOutputReports(outputPaths) {
  if (!window.hdrTranscoder || !window.hdrTranscoder.readInfoJson || !Array.isArray(outputPaths) || outputPaths.length === 0) {
    return;
  }
  try {
    const reports = await window.hdrTranscoder.readInfoJson(outputPaths);
    state.outputReports = Array.isArray(reports) ? reports : [];
    renderOutputReports();
  } catch (error) {
    appendLog(`${t("messages.infoReadFailed", { message: error && error.message ? error.message : String(error) })}\n`, "stderr");
  }
}

function handleConversionDone(result) {
  updateBusyState(false);

  if (result.ok) {
    setQueueFinished(true);
    setStatus("Done", "success");
    const outputCount = Array.isArray(result.outputPaths) ? result.outputPaths.length : 0;
    setSummary(outputCount > 0 ? t("messages.finishedChecked", { count: outputCount }) : t("messages.finished"));
    if (elements.infoJsonInput.checked) {
      loadOutputReports(result.outputPaths || []);
    }
  } else if (result.canceled) {
    setStatus("Canceled", "idle");
    setSummary(t("messages.conversionCanceled"));
  } else {
    setQueueFinished(false);
    setStatus("Error", "error");
    setSummary(result.message || t("messages.conversionFailed"));
  }

  appendLog(`\n--- ${result.message || t("messages.conversionEnded")} ---\n`, "system");
}

async function runRuntimeCheck() {
  if (!window.hdrTranscoder || !window.hdrTranscoder.checkRuntime) {
    return;
  }
  elements.runtimeStatus.textContent = t("messages.checkingRuntime");
  elements.runtimeStatus.className = "runtime-status pending";
  try {
    renderRuntimeStatus(await window.hdrTranscoder.checkRuntime());
  } catch (error) {
    renderRuntimeStatus({
      ok: false,
      missingTools: [],
      dependencyErrors: [{ package: "runtime", error: error && error.message ? error.message : String(error) }],
    });
  }
}

function setLogFilter(filter) {
  state.logFilter = filter;
  document.querySelectorAll("[data-log-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.logFilter === filter);
  });
  renderLog();
}

function toggleLogDrawer() {
  const collapsed = elements.logDrawer.classList.toggle("collapsed");
  elements.logToggleButton.textContent = collapsed ? t("ui.expand") : t("ui.collapse");
}

function bindEvents() {
  if (elements.languageSelect) {
    elements.languageSelect.addEventListener("change", () => setLanguage(elements.languageSelect.value));
  }
  document.querySelectorAll("[data-help]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeHelpTopic = button.dataset.help;
      renderHelp(state.activeHelpTopic);
    });
  });
  document.querySelectorAll("[data-log-filter]").forEach((button) => {
    button.addEventListener("click", () => setLogFilter(button.dataset.logFilter));
  });

  elements.clearLogButton.addEventListener("click", () => {
    state.logs = [];
    renderLog();
  });
  elements.logToggleButton.addEventListener("click", toggleLogDrawer);
  elements.formatSelect.addEventListener("change", updateFormatState);
  elements.jxlModeSelect.addEventListener("change", updateFormatState);
  elements.losslessInput.addEventListener("change", updateFormatState);
  elements.bt2020PqTiffInput.addEventListener("change", updateFormatState);
  elements.uhdrBackendSelect.addEventListener("change", updateFormatState);
  elements.advancedPanel.addEventListener("toggle", () => {
    state.advancedOpen = elements.advancedPanel.open;
  });
}

function initializeUnavailable() {
  updateBusyState(true);
  elements.cancelButton.disabled = true;
  elements.clearLogButton.disabled = false;
  setStatus("Unavailable", "error");
  setSummary(t("messages.preloadUnavailable"));
  appendLog(`${t("messages.preloadUnavailable")}\n`, "stderr");
}

function initializeApp() {
  initializeLanguage();
  bindEvents();
  renderStatusBadge();
  renderHelp("");
  renderQueue();
  renderInspector();
  renderOutputReports();
  renderLog();
  updateFormatState();
  setPathDisplay(elements.outputPath, "", t("ui.defaultOutputLocation"));

  if (!window.hdrTranscoder) {
    initializeUnavailable();
    return;
  }

  elements.pickFilesButton.addEventListener("click", chooseInputFiles);
  elements.pickDirectoryButton.addEventListener("click", chooseInputDirectory);
  elements.pickOutputButton.addEventListener("click", chooseOutputDirectory);
  elements.runtimeCheckButton.addEventListener("click", runRuntimeCheck);
  elements.clearQueueButton.addEventListener("click", clearQueue);
  elements.clearOutputButton.addEventListener("click", clearOutputDirectory);
  elements.form.addEventListener("submit", startConversion);
  elements.cancelButton.addEventListener("click", cancelConversion);

  window.hdrTranscoder.onConversionOutput((payload) => {
    appendLog(payload.text, payload.stream);
  });

  window.hdrTranscoder.onConversionDone(handleConversionDone);
  if (window.hdrTranscoder.onRuntimeStatus) {
    window.hdrTranscoder.onRuntimeStatus(renderRuntimeStatus);
  }
  runRuntimeCheck();
}

initializeApp();
