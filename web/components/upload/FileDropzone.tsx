"use client";

import { useCallback } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { UploadCloud } from "lucide-react";

import { cn } from "@/lib/utils";

const ACCEPT = {
  "application/x-hwp": [".hwp"],
  "application/hwp": [".hwp"],
  "application/haansofthwp": [".hwp"],
  "application/vnd.hancom.hwpx": [".hwpx"],
  "application/pdf": [".pdf"],
  "text/markdown": [".md"],
  "text/plain": [".md"],
};

const MAX_SIZE = 30 * 1024 * 1024; // 30MB

export function FileDropzone({
  onFile,
  disabled,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const onDrop = useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      if (rejected.length > 0) return;
      const file = accepted[0];
      if (file) onFile(file);
    },
    [onFile]
  );

  const { getRootProps, getInputProps, isDragActive, fileRejections } =
    useDropzone({
      onDrop,
      accept: ACCEPT,
      maxSize: MAX_SIZE,
      multiple: false,
      disabled,
    });

  const rejectionMsg =
    fileRejections.length > 0
      ? fileRejections[0].errors[0]?.code === "file-too-large"
        ? "파일이 너무 큽니다 (최대 30MB)."
        : "지원하지 않는 형식입니다. HWP·HWPX·PDF·MD만 가능합니다."
      : null;

  return (
    <div>
      <div
        {...getRootProps()}
        className={cn(
          "group flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-16 text-center transition-colors",
          isDragActive
            ? "border-brand bg-[color-mix(in_oklab,var(--brand)_8%,transparent)]"
            : "border-border bg-card/40 hover:border-muted-foreground/50 hover:bg-card/70",
          disabled && "pointer-events-none opacity-60"
        )}
      >
        <input {...getInputProps()} />
        <span
          className={cn(
            "grid size-12 place-items-center rounded-full border border-border bg-secondary/50 transition-transform group-hover:scale-105",
            isDragActive && "border-brand"
          )}
        >
          <UploadCloud
            className={cn(
              "size-5 text-muted-foreground",
              isDragActive && "text-brand"
            )}
          />
        </span>
        <div>
          <p className="text-[14px] font-medium text-foreground">
            {isDragActive
              ? "여기에 놓으세요"
              : "파일을 드래그하거나 클릭해 업로드"}
          </p>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
            HWP · HWPX · PDF · MD · 최대 30MB
          </p>
        </div>
      </div>

      {rejectionMsg && (
        <p className="mt-2 text-[12px] text-[var(--status-error)]">
          {rejectionMsg}
        </p>
      )}
      <p className="mt-3 text-center text-[11px] text-muted-foreground">
        ※ 업로드한 파일은 분석 목적으로만 처리됩니다.
      </p>
    </div>
  );
}
