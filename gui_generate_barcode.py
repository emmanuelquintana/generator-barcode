# -*- coding: utf-8 -*-
"""
GUI PRO+ (azul oscuro) – Etiquetas 51×25 mm desde CSV
• Vista previa y PDF equivalentes
• Título y SKU: UNA SOLA LÍNEA (sin "…" ni salto a 2 líneas)
• Tú ajustas tamaños hasta que quepan
• Botones +/- grandes (mejor UX) con estilo ttk

Requisitos:
    pip install reportlab pandas pillow python-barcode
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging, re, io
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageTk, Image
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# ====== Constantes etiqueta ======
LABEL_W_MM = 51.0
LABEL_H_MM = 25.0
PT_TO_MM   = 25.4/72.0     # 1 pt = 0.352777… mm
PREVIEW_SCALE = 6          # px por mm (preview a escala real)

# ====== Valores por defecto ======
NAME_FONT_SIZE_DEFAULT = 8.5
SKU_FONT_SIZE_DEFAULT  = 8.0
CODE_TEXT_SIZE_DEFAULT = 9.0

BARCODE_HEIGHT_MM_DEFAULT = 10.0
BARCODE_WIDTH_MM_DEFAULT  = 45.5

MARGIN_LEFT_MM_DEFAULT, MARGIN_RIGHT_MM_DEFAULT = 3.0, 3.0
MARGIN_TOP_MM_DEFAULT,  MARGIN_BOTTOM_MM_DEFAULT= 3.5, 1.0

LINE_SPACING_MM_DEFAULT = 3.4       # distancia entre línea del título y la siguiente baseline
TITLE_SKU_SPACE_MM_DEFAULT = 0.8    # espacio vertical entre título y SKU
SKU_SPACING_MM_DEFAULT  = 0.0       # espacio después del SKU (antes del código)

# (Se mantienen por compatibilidad aunque ahora no se usan para envolver texto)
TITLE_MAX_W_MM_DEFAULT = 45.0
SKU_MAX_W_MM_DEFAULT   = 45.0

# --------- Columnas candidatas ---------
CANDIDATES = {
    "nombre":  ["nombre","name","titulo","producto","descripcion","descripcion_corta"],
    "sku":     ["sku","modelo","clave","referencia"],
    "barcode": ["barcode","ean","gtin","codigo","codigo_barras","codigo_de_barras","cod_barras"],
    "cantidad":["cantifad","cantidad","qty","cantidad_de_etiquetas","num_etiquetas"]
}

# ================== Utilidades CSV/columnas ==================
def norm_col(s): return re.sub(r"[^a-z0-9]+","_", s.strip().lower())

def read_csv_any(p: Path):
    try: return pd.read_csv(p, encoding="utf-8")
    except Exception: return pd.read_csv(p, encoding="latin-1")

def map_columns(df: pd.DataFrame, overrides: dict):
    df = df.rename(columns={c:norm_col(c) for c in df.columns})
    mapping = {}
    for k,v in overrides.items():
        if v: mapping[k] = norm_col(v)

    for t, opts in CANDIDATES.items():
        if t in mapping: continue
        for o in opts:
            if norm_col(o) in df.columns:
                mapping[t] = norm_col(o); break

    if "barcode" not in mapping:
        for c in df.columns:
            s = df[c].astype(str).str.replace(r"\D","", regex=True)
            if s.str.fullmatch(r"\d{12,14}").fillna(False).mean() > 0.5:
                mapping["barcode"] = c; break
    if "sku" not in mapping:
        for c in df.columns:
            if "sku" in c or "modelo" in c or "referencia" in c:
                mapping["sku"]=c; break
    if "nombre" not in mapping:
        txt=[(df[c].astype(str).str.len().mean(), c) for c in df.columns if df[c].dtype==object]
        if txt: mapping["nombre"]=sorted(txt,reverse=True)[0][1]
    if "cantidad" not in mapping:
        df["_cantidad_default"]=1; mapping["cantidad"]="_cantidad_default"
    return mapping, df

def parse_int_safe(x, default=1):
    try:
        import pandas as _pd
        if _pd.isna(x) or (isinstance(x,str) and x.strip()==""): return default
        return max(0, int(float(str(x).strip())))
    except Exception:
        return default

def build_labels(df, mapping):
    out=[]
    for _,r in df.iterrows():
        nombre  = str(r.get(mapping["nombre"], "")).strip()
        sku     = str(r.get(mapping["sku"], "")).strip()
        barcode = re.sub(r"\D","", str(r.get(mapping["barcode"], "")).strip())
        cant    = parse_int_safe(r.get(mapping["cantidad"]),1)
        for _ in range(cant): out.append({"nombre":nombre,"sku":sku,"barcode":barcode})
    return out

# ================== Fuentes (PIL + ReportLab) ==================
def _find_font_path():
    for p in [
        "C:/Windows/Fonts/arial.ttf","C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf","/Library/Fonts/Arial.ttf"
    ]:
        if Path(p).exists(): return p
    return None

def get_font_px_from_pt(pt):
    size_px = max(1, int(round(pt * PT_TO_MM * PREVIEW_SCALE)))
    path=_find_font_path()
    if path:
        try: return ImageFont.truetype(path, size_px)
        except Exception: pass
    try: return ImageFont.truetype("DejaVuSans.ttf", size_px)
    except Exception: return ImageFont.load_default()

def register_reportlab_font():
    try:
        path=_find_font_path()
        if path: pdfmetrics.registerFont(TTFont("UIFont", path)); return "UIFont"
        pdfmetrics.registerFont(TTFont("DejaVu","/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")); return "DejaVu"
    except Exception:
        return "Helvetica"

# ================== Barcode ==================
def make_barcode_image(code: str, width_px: int, height_px: int) -> Image.Image:
    try:
        import barcode
        from barcode.writer import ImageWriter
        bc_type = 'ean13' if re.fullmatch(r"\d{13}", code or "") else 'code128'
        cls = barcode.get_barcode_class(bc_type)
        bc = cls(code, writer=ImageWriter())
        base = bc.render(writer_options={
            "module_width": 0.18, "module_height": max(1,height_px//3),
            "quiet_zone": 2.0, "font_size": 0, "text": ""
        })
    except Exception:
        base = Image.new("RGB",(max(1,width_px),max(1,height_px)),"black")
    return base.resize((max(1,width_px),max(1,height_px)), Image.NEAREST)

def barcode_png_bytes(code: str, width_mm: float, height_mm: float, dpi=300) -> bytes:
    px_w = int(width_mm * dpi / 25.4)
    px_h = int(height_mm * dpi / 25.4)
    img = make_barcode_image(code, px_w, px_h)
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()

# ================== Medidas texto / dibujo ==================
def pil_text_width_px(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    try:
        b = draw.textbbox((0,0), text, font=font)
        return b[2]-b[0]
    except Exception:
        return font.getsize(text)[0]

def draw_centered_baseline(draw, x_c, baseline_y, text, font, fill="black"):
    try:
        ascent, _ = font.getmetrics()
    except Exception:
        ascent = font.size
    w = pil_text_width_px(draw, text, font)
    top = int(round(baseline_y - ascent))
    draw.text((int(round(x_c - w/2)), top), text, font=font, fill=fill)

# ================== PREVIEW ==================
def build_preview_image(rec, *,
                        name_fs, sku_fs, code_fs,
                        bar_h_mm, bar_w_mm,
                        m_left_mm, m_right_mm, m_top_mm, m_bottom_mm,
                        line_spacing_mm, title_sku_space_mm, sku_spacing_mm,
                        title_max_w_mm, sku_max_w_mm):
    """
    Versión single-line: título y SKU en 1 línea, sin truncar ni '...'.
    title_max_w_mm y sku_max_w_mm no se usan aquí (se conservan por compatibilidad).
    """
    scale = PREVIEW_SCALE
    W_px = int(LABEL_W_MM * scale)
    H_px = int(LABEL_H_MM * scale)
    img = Image.new("RGB",(W_px,H_px),"#0b1220")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0,0,W_px-1,H_px-1], fill="white", outline="#334155")

    m_left, m_right = int(m_left_mm*scale), int(m_right_mm*scale)
    m_top, m_bottom = int(m_top_mm*scale), int(m_bottom_mm*scale)
    usable_w_px = W_px - (m_left + m_right)

    name_font = get_font_px_from_pt(name_fs)
    sku_font  = get_font_px_from_pt(sku_fs)
    code_font = get_font_px_from_pt(code_fs)

    # ---- TÍTULO: una sola línea (sin '...')
    y_baseline = m_top
    title_line = rec.get("nombre","") or ""
    draw_centered_baseline(draw, W_px//2, y_baseline, title_line, name_font)
    y_baseline += int(line_spacing_mm*scale)

    # Espacio Título ↔ SKU
    y_baseline += int(title_sku_space_mm*scale)

    # ---- SKU: una sola línea (sin '...')
    sku_line = rec.get("sku","") or ""
    draw_centered_baseline(draw, W_px//2, y_baseline, sku_line, sku_font)

    # Espacio después del SKU
    y_baseline += int(sku_spacing_mm*scale)

    # ---- Código de barras
    bc_top = y_baseline + int(2*scale)
    bc_h   = int(float(bar_h_mm) * scale)
    bc_w   = int(min(usable_w_px, float(bar_w_mm) * scale))
    code   = re.sub(r"\D","", rec.get("barcode","") or "")
    bc_img = make_barcode_image(code, bc_w, bc_h)
    img.paste(bc_img, (W_px//2 - bc_img.width//2, bc_top))

    # Texto del código a 1.5 mm del margen inferior
    baseline_bottom = H_px - int((m_bottom_mm + 1.5) * scale)
    draw_centered_baseline(draw, W_px//2, baseline_bottom, code, code_font)

    draw.rectangle([0,0,W_px-1,H_px-1], outline="#0ea5e9")
    return img

# ================== PDF ==================
def draw_label_pdf(c, W, H, rec, *,
                   base_font="Helvetica",
                   name_fs=NAME_FONT_SIZE_DEFAULT, sku_fs=SKU_FONT_SIZE_DEFAULT, code_fs=CODE_TEXT_SIZE_DEFAULT,
                   bar_h_mm=BARCODE_HEIGHT_MM_DEFAULT, bar_w_mm=BARCODE_WIDTH_MM_DEFAULT,
                   m_left_mm=MARGIN_LEFT_MM_DEFAULT, m_right_mm=MARGIN_RIGHT_MM_DEFAULT,
                   m_top_mm=MARGIN_TOP_MM_DEFAULT, m_bottom_mm=MARGIN_BOTTOM_MM_DEFAULT,
                   line_spacing_mm=LINE_SPACING_MM_DEFAULT, title_sku_space_mm=TITLE_SKU_SPACE_MM_DEFAULT, sku_spacing_mm=SKU_SPACING_MM_DEFAULT,
                   title_max_w_mm=TITLE_MAX_W_MM_DEFAULT, sku_max_w_mm=SKU_MAX_W_MM_DEFAULT):
    """
    Versión single-line también para PDF: sin truncar ni saltos.
    """
    RLMM = mm
    margin_left, margin_right = float(m_left_mm)*RLMM, float(m_right_mm)*RLMM
    margin_top,  margin_bottom= float(m_top_mm)*RLMM, float(m_bottom_mm)*RLMM
    usable_w = W - (margin_left + margin_right)

    # ---- TÍTULO (una línea)
    y = H - margin_top
    c.setFont(base_font, float(name_fs))
    c.drawCentredString(W/2, y, rec["nombre"] or "")
    y -= float(line_spacing_mm)*RLMM

    # Espacio Título ↔ SKU
    y -= float(title_sku_space_mm)*RLMM

    # ---- SKU (una línea)
    c.setFont(base_font, float(sku_fs))
    c.drawCentredString(W/2, y, (rec["sku"] or ""))
    y -= float(sku_spacing_mm)*RLMM

    # ---- Código de barras
    code = re.sub(r"\D","", rec["barcode"] or "")
    desired_w_mm = float(bar_w_mm)
    if desired_w_mm*RLMM > usable_w:
        desired_w_mm = usable_w/RLMM
    png_bytes = barcode_png_bytes(code, desired_w_mm, float(bar_h_mm), dpi=300)
    img = ImageReader(io.BytesIO(png_bytes))
    x = margin_left + (usable_w - desired_w_mm*RLMM)/2.0
    top = y - 2*RLMM - float(bar_h_mm)*RLMM
    c.drawImage(img, x, top, width=desired_w_mm*RLMM, height=float(bar_h_mm)*RLMM,
                preserveAspectRatio=False, mask='auto')

    # Texto del código
    c.setFont(base_font, float(code_fs))
    c.drawCentredString(W/2, margin_bottom + 1.5*RLMM, code)

# ================== UI: control +/− grande ==================
class PlusMinus(tk.Frame):
    """
    Control numérico con Entry centrado y botones +/- grandes (ttk).
    """
    def __init__(self, parent, label, var: tk.DoubleVar, minv, maxv, step, on_change=None):
        super().__init__(parent, bg="#0e1a34")
        self.var, self.minv, self.maxv, self.step = var, float(minv), float(maxv), float(step)
        self.on_change = on_change

        ttk.Label(self, text=label).grid(row=0, column=0, columnspan=3, sticky="w")

        self.btn_minus = ttk.Button(self, text="−", style="Big.TButton", command=self.dec, width=2)
        self.btn_plus  = ttk.Button(self, text="+", style="Big.TButton", command=self.inc, width=2)
        self.entry = tk.Entry(self, textvariable=self.var, justify="right",
                              font=("Segoe UI", 11), width=8, relief="solid",
                              bg="#0f172a", fg="#e5e7eb", insertbackground="#e5e7eb")

        self.btn_minus.grid(row=1, column=0, padx=(0,8), pady=2)
        self.entry.grid(row=1, column=1, padx=8, pady=2)
        self.btn_plus.grid(row=1, column=2, padx=(8,0), pady=2)

        self.entry.bind("<Return>", lambda e: self._clamp_and_fire())
        self.entry.bind("<FocusOut>", lambda e: self._clamp_and_fire())

    def _clamp_and_fire(self):
        try: v=float(self.var.get())
        except Exception: v=self.minv
        v=max(self.minv, min(self.maxv, v))
        self.var.set(round(v, 3))
        if self.on_change: self.on_change()

    def inc(self):
        try: v=float(self.var.get())
        except Exception: v=self.minv
        v=min(self.maxv, v+self.step)
        self.var.set(round(v,3))
        if self.on_change: self.on_change()

    def dec(self):
        try: v=float(self.var.get())
        except Exception: v=self.minv
        v=max(self.minv, v-self.step)
        self.var.set(round(v,3))
        if self.on_change: self.on_change()

# ================== APP ==================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Etiquetas 51x25 mm – PRO+ (Single-line)")
        self.geometry("1120x760")
        self.configure(bg="#0b1220")

        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("Dark.TFrame", background="#0b1220")
        style.configure("Card.TFrame", background="#0e1a34")
        style.configure("TLabel", background="#0e1a34", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="#0b1220", foreground="#93c5fd", font=("Segoe UI Semibold", 13))
        style.configure("TButton", background="#1d4ed8", foreground="white", padding=8)
        style.map("TButton", background=[("active","#2563eb")])
        style.configure("Big.TButton", font=("Segoe UI", 12), padding=6)

        # Vars
        self.csv_path = tk.StringVar()
        self.out_folder = tk.StringVar(value=str(Path.cwd()))
        self.out_filename = tk.StringVar(value="etiquetas_51x25mm.pdf")
        self.col_nombre = tk.StringVar(); self.col_sku = tk.StringVar()
        self.col_barcode = tk.StringVar(); self.col_cantidad = tk.StringVar()

        self.name_fs = tk.DoubleVar(value=NAME_FONT_SIZE_DEFAULT)
        self.sku_fs  = tk.DoubleVar(value=SKU_FONT_SIZE_DEFAULT)
        self.code_fs = tk.DoubleVar(value=CODE_TEXT_SIZE_DEFAULT)
        self.bar_h   = tk.DoubleVar(value=BARCODE_HEIGHT_MM_DEFAULT)
        self.bar_w   = tk.DoubleVar(value=BARCODE_WIDTH_MM_DEFAULT)

        self.m_left  = tk.DoubleVar(value=MARGIN_LEFT_MM_DEFAULT)
        self.m_right = tk.DoubleVar(value=MARGIN_RIGHT_MM_DEFAULT)
        self.m_top   = tk.DoubleVar(value=MARGIN_TOP_MM_DEFAULT)
        self.m_bottom= tk.DoubleVar(value=MARGIN_BOTTOM_MM_DEFAULT)

        self.line_spacing = tk.DoubleVar(value=LINE_SPACING_MM_DEFAULT)
        self.title_sku_space = tk.DoubleVar(value=TITLE_SKU_SPACE_MM_DEFAULT)
        self.sku_spacing  = tk.DoubleVar(value=SKU_SPACING_MM_DEFAULT)

        self.title_max_w = tk.DoubleVar(value=TITLE_MAX_W_MM_DEFAULT)  # sin uso actual
        self.sku_max_w   = tk.DoubleVar(value=SKU_MAX_W_MM_DEFAULT)    # sin uso actual

        self.df_cached=None; self.preview_photo=None

        self.build_ui()

        for v in (self.name_fs,self.sku_fs,self.code_fs,self.bar_h,self.bar_w,
                  self.m_left,self.m_right,self.m_top,self.m_bottom,
                  self.line_spacing,self.title_sku_space,self.sku_spacing,
                  self.title_max_w,self.sku_max_w):
            v.trace_add("write", lambda *a: self._safe_preview())

    def build_ui(self):
        root = ttk.Frame(self, style="Dark.TFrame"); root.pack(fill="both", expand=True, padx=16, pady=16)
        ttk.Label(root, text="Generador de Etiquetas 51×25 mm", style="Header.TLabel").pack(anchor="w", pady=(0,8))

        top = ttk.Frame(root, style="Card.TFrame"); top.pack(fill="x", pady=8, ipady=6, ipadx=6)

        f1 = ttk.Frame(top, style="Card.TFrame"); f1.pack(fill="x", pady=6, padx=8)
        ttk.Label(f1, text="CSV:").pack(side="left", padx=(0,8))
        ttk.Entry(f1, textvariable=self.csv_path, width=62).pack(side="left", padx=(0,8))
        ttk.Button(f1, text="Elegir CSV", command=self.choose_csv).pack(side="left")
        ttk.Label(f1, text="Carpeta destino:").pack(side="left", padx=(16,8))
        ttk.Entry(f1, textvariable=self.out_folder, width=42).pack(side="left", padx=(0,8))
        ttk.Button(f1, text="Seleccionar", command=self.choose_folder).pack(side="left")

        f2 = ttk.Frame(top, style="Card.TFrame"); f2.pack(fill="x", pady=6, padx=8)
        ttk.Label(f2, text="Nombre PDF:").pack(side="left", padx=(0,8))
        ttk.Entry(f2, textvariable=self.out_filename, width=32).pack(side="left", padx=(0,8))
        ttk.Button(f2, text="Autodetectar columnas", command=self.autodetect).pack(side="left", padx=(16,0))

        f3 = ttk.Frame(top, style="Card.TFrame"); f3.pack(fill="x", pady=6, padx=8)
        for label, var in [("Columna Nombre", self.col_nombre),
                           ("SKU", self.col_sku),
                           ("Código", self.col_barcode),
                           ("Cantidad", self.col_cantidad)]:
            cell = ttk.Frame(f3, style="Card.TFrame"); cell.pack(side="left", padx=(0,16))
            ttk.Label(cell, text=label+":").pack(anchor="w")
            ttk.Entry(cell, textvariable=var, width=22).pack(anchor="w")

        f4 = ttk.Frame(top, style="Card.TFrame"); f4.pack(fill="x", pady=8, padx=8)
        for lbl,var,a,b,st in [
            ("Letra NOMBRE (pt)", self.name_fs, 6, 16, 0.5),
            ("Letra SKU (pt)",    self.sku_fs,  5, 14, 0.5),
            ("Letra CÓDIGO (pt)", self.code_fs, 6, 16, 0.5),
            ("Altura Código (mm)",self.bar_h,   5, 14, 0.5),
            ("Ancho Código (mm)", self.bar_w,   20, 50,0.5),
        ]:
            PlusMinus(f4, lbl, var, a, b, st, on_change=self._safe_preview).pack(side="left", padx=(0,18))

        f5 = ttk.Frame(top, style="Card.TFrame"); f5.pack(fill="x", pady=8, padx=8)
        for lbl,var,a,b,st in [
            ("Margen Izq (mm)", self.m_left, 0, 10, 0.5),
            ("Margen Der (mm)", self.m_right,0, 10, 0.5),
            ("Margen Arriba (mm)", self.m_top,0, 10, 0.5),
            ("Margen Abajo (mm)",  self.m_bottom,0,10, 0.5),
        ]:
            PlusMinus(f5, lbl, var, a, b, st, on_change=self._safe_preview).pack(side="left", padx=(0,18))

        f6 = ttk.Frame(top, style="Card.TFrame"); f6.pack(fill="x", pady=8, padx=8)
        PlusMinus(f6, "Espacio entre líneas Título (mm)", self.line_spacing, 2.0, 6.0, 0.2, on_change=self._safe_preview).pack(side="left", padx=(0,18))
        PlusMinus(f6, "Espacio Título ↔ SKU (mm)", self.title_sku_space, 0.0, 6.0, 0.2, on_change=self._safe_preview).pack(side="left", padx=(0,18))
        PlusMinus(f6, "Espacio después del SKU (mm)", self.sku_spacing, 0.0, 8.0, 0.2, on_change=self._safe_preview).pack(side="left", padx=(0,18))

        # (Se mantienen por si en el futuro reactivas el ajuste por ancho)
        f7 = ttk.Frame(top, style="Card.TFrame"); f7.pack(fill="x", pady=8, padx=8)
        PlusMinus(f7, "Ancho TÍTULO (mm)", self.title_max_w, 20.0, 50.0, 0.5, on_change=self._safe_preview).pack(side="left", padx=(0,18))
        PlusMinus(f7, "Ancho SKU (mm)",    self.sku_max_w,   20.0, 50.0, 0.5, on_change=self._safe_preview).pack(side="left", padx=(0,18))

        actions = ttk.Frame(top, style="Card.TFrame"); actions.pack(fill="x", pady=10, padx=8)
        ttk.Button(actions, text="Generar Vista Previa", command=self.preview).pack(side="left")
        ttk.Button(actions, text="Generar PDF", command=self.generate).pack(side="left", padx=8)

        preview_card = ttk.Frame(root, style="Card.TFrame"); preview_card.pack(fill="both", expand=True, pady=8, ipady=8, ipadx=8)
        ttk.Label(preview_card, text="Vista previa (1 etiqueta):").pack(anchor="w")
        self.preview_canvas = tk.Canvas(preview_card,
                                        width=int(LABEL_W_MM*PREVIEW_SCALE),
                                        height=int(LABEL_H_MM*PREVIEW_SCALE),
                                        bg="#0b1220", highlightthickness=1, highlightbackground="#334155")
        self.preview_canvas.pack(pady=10)

        self.status = tk.StringVar(value="Listo. Ajusta con +/− y genera vista previa.")
        ttk.Label(root, textvariable=self.status, style="Header.TLabel").pack(anchor="w", pady=(8,0))

    # ---------- lógica ----------
    def _safe_preview(self): 
        try: self.preview()
        except Exception: pass

    def choose_csv(self):
        p = filedialog.askopenfilename(title="Seleccionar CSV", filetypes=[("CSV","*.csv"),("Todos","*.*")])
        if p:
            self.csv_path.set(p)
            try: self.df_cached = read_csv_any(Path(p)); self.status.set("CSV cargado. Puedes autodetectar columnas.")
            except Exception as e: messagebox.showerror("Error", f"No se pudo leer el CSV:\n{e}")

    def choose_folder(self):
        f = filedialog.askdirectory(title="Seleccionar carpeta destino")
        if f: self.out_folder.set(f)

    def autodetect(self):
        if not self.csv_path.get(): messagebox.showwarning("Falta CSV","Primero elige un archivo CSV."); return
        try:
            df = self.df_cached if self.df_cached is not None else read_csv_any(Path(self.csv_path.get()))
            mapping, _ = map_columns(df, {
                "nombre":self.col_nombre.get() or None,
                "sku":self.col_sku.get() or None,
                "barcode":self.col_barcode.get() or None,
                "cantidad":self.col_cantidad.get() or None
            })
            rev = {norm_col(c):c for c in df.columns}
            self.col_nombre.set(rev.get(mapping.get("nombre",""),""))
            self.col_sku.set(rev.get(mapping.get("sku",""),""))
            self.col_barcode.set(rev.get(mapping.get("barcode",""),""))
            self.col_cantidad.set(rev.get(mapping.get("cantidad",""),""))
            self.status.set("Columnas autodetectadas.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo autodetectar:\n{e}")

    def get_mapping_df(self):
        if not self.csv_path.get(): raise RuntimeError("Selecciona primero un CSV.")
        df = self.df_cached if self.df_cached is not None else read_csv_any(Path(self.csv_path.get()))
        return map_columns(df, {
            "nombre":self.col_nombre.get() or None, "sku":self.col_sku.get() or None,
            "barcode":self.col_barcode.get() or None,"cantidad":self.col_cantidad.get() or None
        })

    def preview(self):
        mapping, df = self.get_mapping_df()
        if df.empty: messagebox.showwarning("CSV vacío","El archivo CSV no tiene filas."); return
        r = df.iloc[0]
        rec = {"nombre":str(r.get(mapping["nombre"],"")).strip(),
               "sku":str(r.get(mapping["sku"],"")).strip(),
               "barcode":re.sub(r"\D","", str(r.get(mapping["barcode"],"")).strip())}

        img = build_preview_image(
            rec,
            name_fs=self.name_fs.get(), sku_fs=self.sku_fs.get(), code_fs=self.code_fs.get(),
            bar_h_mm=self.bar_h.get(), bar_w_mm=self.bar_w.get(),
            m_left_mm=self.m_left.get(), m_right_mm=self.m_right.get(),
            m_top_mm=self.m_top.get(),   m_bottom_mm=self.m_bottom.get(),
            line_spacing_mm=self.line_spacing.get(),
            title_sku_space_mm=self.title_sku_space.get(),
            sku_spacing_mm=self.sku_spacing.get(),
            title_max_w_mm=self.title_max_w.get(),
            sku_max_w_mm=self.sku_max_w.get()
        )
        self.preview_photo = ImageTk.PhotoImage(img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0,0,anchor="nw", image=self.preview_photo)
        self.status.set("Vista previa actualizada.")

    def generate(self):
        if not self.out_folder.get():
            messagebox.showwarning("Falta carpeta","Selecciona una carpeta destino."); return
        out_path = str(Path(self.out_folder.get()) / (self.out_filename.get() or "etiquetas_51x25mm.pdf"))

        log_path = Path(out_path).with_suffix(".log")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                            handlers=[logging.FileHandler(log_path, encoding="utf-8")])

        try:
            base_font = register_reportlab_font()
            mapping, df = self.get_mapping_df()
            labels = build_labels(df, mapping)

            W,H = LABEL_W_MM*mm, LABEL_H_MM*mm
            c = pdf_canvas.Canvas(out_path, pagesize=(W,H))
            for rec in labels:
                draw_label_pdf(
                    c, W, H, rec, base_font=base_font,
                    name_fs=self.name_fs.get(), sku_fs=self.sku_fs.get(), code_fs=self.code_fs.get(),
                    bar_h_mm=self.bar_h.get(), bar_w_mm=self.bar_w.get(),
                    m_left_mm=self.m_left.get(), m_right_mm=self.m_right.get(),
                    m_top_mm=self.m_top.get(),   m_bottom_mm=self.m_bottom.get(),
                    line_spacing_mm=self.line_spacing.get(),
                    title_sku_space_mm=self.title_sku_space.get(),
                    sku_spacing_mm=self.sku_spacing.get(),
                    title_max_w_mm=self.title_max_w.get(),
                    sku_max_w_mm=self.sku_max_w.get()
                )
                c.showPage()
            c.save()
            messagebox.showinfo("Éxito", f"PDF generado:\n{out_path}\nLog:\n{log_path}")
            self.status.set("PDF generado correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error:\n{e}")
            self.status.set("Error en la generación.")

if __name__ == "__main__":
    App().mainloop()
