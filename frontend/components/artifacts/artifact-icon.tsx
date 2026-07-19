/**
 * Kind → icon mapping for artifact cards/panels (ARTIFACTS.md §12).
 *
 * A single source so the card, the panel header, and any future surface render the
 * same glyph per kind. Unknown kinds fall back to a generic file icon.
 */
import {
  FileArchive,
  FileCode,
  FileJson,
  FileSpreadsheet,
  FileText,
  FileType,
  Presentation,
  Table2,
  type LucideIcon,
} from "lucide-react";
import type { ArtifactFileKind } from "@/types/agui";

const ICONS: Record<ArtifactFileKind, LucideIcon> = {
  code: FileCode,
  markdown: FileText,
  json: FileJson,
  csv: Table2,
  xlsx: FileSpreadsheet,
  pptx: Presentation,
  pdf: FileText,
  docx: FileText,
  image: FileType,
  archive: FileArchive,
};

export function artifactIcon(kind: ArtifactFileKind): LucideIcon {
  return ICONS[kind] ?? FileType;
}
