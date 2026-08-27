---
name: Devlet Arşiv Yönetimi Sistemi
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#44474e'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#74777f'
  outline-variant: '#c4c6cf'
  surface-tint: '#465f88'
  primary: '#002046'
  on-primary: '#ffffff'
  primary-container: '#1b365d'
  on-primary-container: '#87a0cd'
  inverse-primary: '#aec7f7'
  secondary: '#00658d'
  on-secondary: '#ffffff'
  secondary-container: '#41befd'
  on-secondary-container: '#004b69'
  tertiary: '#1d2123'
  on-tertiary: '#ffffff'
  tertiary-container: '#333638'
  on-tertiary-container: '#9c9fa1'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d6e3ff'
  primary-fixed-dim: '#aec7f7'
  on-primary-fixed: '#001b3d'
  on-primary-fixed-variant: '#2e476f'
  secondary-fixed: '#c6e7ff'
  secondary-fixed-dim: '#81cfff'
  on-secondary-fixed: '#001e2d'
  on-secondary-fixed-variant: '#004c6b'
  tertiary-fixed: '#e0e3e5'
  tertiary-fixed-dim: '#c4c7c9'
  on-tertiary-fixed: '#191c1e'
  on-tertiary-fixed-variant: '#444749'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-max-width: 1440px
  sidebar-width: 260px
  sidebar-collapsed: 72px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

The design system is engineered for the high-stakes environment of government document management, where precision and authority are paramount. The visual language follows a **Corporate / Modern** aesthetic with a lean toward **Minimalism** to reduce cognitive load when processing dense regulatory data. 

The user interface prioritizes clarity, utilizing generous whitespace and a structured grid to convey a sense of institutional stability. The integration of AI features is handled with subtle technical accents rather than flashy graphics, ensuring the technology feels like a dependable tool rather than an experimental addition. The emotional response should be one of absolute trust, efficiency, and professional calm.

## Colors

The palette is anchored by **State Blue**, providing a foundation of authority and traditional governance. **Tech Cyan** is used sparingly to highlight AI-driven insights, automated actions, and digital progress.

- **Primary (State Blue):** Used for navigation headers, primary buttons, and institutional branding.
- **Secondary (Tech Cyan):** Used for AI confidence scores, active selection states, and interactive tech elements.
- **Surface Colors:** A range of clean grays (Cool Gray 50-100) are utilized to separate document preview areas from administrative controls.
- **Functional Colors:** Success, Warning, and Error colors follow high-accessibility standards to ensure legal deadlines and missing data are immediately identifiable.

## Typography

The design system utilizes **Inter** for its exceptional legibility in data-dense environments and its neutral, professional character. 

- **Hierarchy:** Strict adherence to font weights is required. Use `SemiBold (600)` for section headers and `Medium (500)` for labels and UI controls.
- **Readability:** For long-form document analysis, `body-lg` is preferred for the OCR (Optical Character Recognition) output text.
- **Localization:** All type scales are optimized for Turkish character sets (e.g., ş, ğ, ı, İ), ensuring consistent vertical alignment and line spacing.

## Layout & Spacing

The layout employs a **fixed grid** system for the main content area, while the document preview and navigation remain flexible.

- **Sidebar:** A collapsible sidebar navigation persists on the left. In its expanded state, it houses the full hierarchy; when collapsed, it provides quick icon-based access.
- **Dual-Pane View:** For document analysis, the screen is split. The left pane (60%) displays the document scan, and the right pane (40%) displays AI-extracted data fields and confidence scores.
- **Density:** This system uses a "Compact" spacing rhythm. Data tables should minimize vertical padding to allow more rows to be visible above the fold.

## Elevation & Depth

This design system utilizes **Tonal Layers** and **Low-Contrast Outlines** to define hierarchy, avoiding heavy shadows to maintain a clean, "official" look.

- **Level 0 (Background):** Base surface in `#F8FAFC`.
- **Level 1 (Cards/Sidebar):** White surfaces with a 1px border in `#E2E8F0`. 
- **Elevation Shadows:** Only used for modal dialogs and dropdown menus to indicate temporary overlays. These shadows are highly diffused: `0px 4px 20px rgba(27, 54, 93, 0.08)`.
- **Active State:** Elements like selected document rows use a subtle Tech Cyan tint (`#E0F2FE`) instead of a shadow.

## Shapes

The shape language is **Soft (0.25rem)**, reflecting a professional balance between rigid traditionalism and modern software.

- **Standard Elements:** Buttons, input fields, and tags use a `4px` corner radius.
- **Large Containers:** Document preview frames and dashboard cards use `8px` (rounded-lg).
- **Status Badges:** Use a slightly higher radius (`12px`) to distinguish them from interactive buttons.

## Components

### Data Tables (Yoğun Veri Tabloları)
Tables are the core of the system. They must feature sticky headers, sortable columns, and row-hover states in State Blue (5% opacity). Status badges within tables must use high-contrast text for legibility.

### AI Confidence Scores (Yapay Zeka Güven Skorları)
Visualized as circular progress rings or segmented bars in Tech Cyan. Scores below 70% should trigger a "Warning" amber tint to alert the user to manual verification.

### Multi-step Progress Indicators (Çok Adımlı Süreç Göstergeleri)
Horizontal stepper at the top of document processing pages. Completed steps use State Blue with a check icon; the current step is highlighted with a Tech Cyan ring.

### Document Preview (Belge Önizleme)
A dedicated frame with integrated zoom, rotate, and text-selection tools. The background of the preview frame is a darker gray (#334155) to make white paper documents pop.

### Inputs & Selects
Form fields use a clear label above the input. Error states must include both a red border and a descriptive error message icon to meet accessibility standards.

### Sidebar (Yan Menü)
The navigation uses a dark background (State Blue) with light text. Active items are indicated by a Tech Cyan vertical bar on the left edge.