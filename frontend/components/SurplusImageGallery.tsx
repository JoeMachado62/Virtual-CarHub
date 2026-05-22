/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useMemo, useState } from "react";

type SurplusImageGalleryProps = {
  images: string[];
  title: string;
  emptyMessage: string;
  selectedImages?: string[];
  onToggleImage?: (image: string) => void;
  cropClassForImage?: (image: string) => string | undefined;
  mode?: "viewer" | "select-grid";
};

export function SurplusImageGallery({
  images,
  title,
  emptyMessage,
  selectedImages = [],
  onToggleImage,
  cropClassForImage,
  mode = "viewer",
}: SurplusImageGalleryProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const selectable = Boolean(onToggleImage);
  const activeImage = images[activeIndex] || "";
  const selectedSet = useMemo(() => new Set(selectedImages), [selectedImages]);
  const imageKey = useMemo(() => images.join("|"), [images]);

  useEffect(() => {
    setActiveIndex(0);
  }, [imageKey]);

  useEffect(() => {
    if (activeIndex >= images.length) {
      setActiveIndex(Math.max(0, images.length - 1));
    }
  }, [activeIndex, images.length]);

  function move(direction: 1 | -1) {
    if (images.length <= 1) return;
    setActiveIndex((current) => (current + direction + images.length) % images.length);
  }

  if (!images.length) {
    return (
      <div className="dashboard-surplus-empty">
        <p>{emptyMessage}</p>
      </div>
    );
  }

  if (mode === "select-grid") {
    return (
      <div className="dashboard-surplus-select-grid">
        {images.map((image, index) => (
          <label
            className={`dashboard-surplus-select-tile${selectedSet.has(image) ? " is-selected" : ""}`}
            key={`${image}-${index}`}
          >
            <input
              type="checkbox"
              checked={selectedSet.has(image)}
              onChange={() => onToggleImage?.(image)}
              aria-label={`Select hidden photo ${index + 1}`}
            />
            <img
              src={image}
              alt={`${title} hidden thumbnail ${index + 1}`}
              className={cropClassForImage?.(image)}
            />
          </label>
        ))}
      </div>
    );
  }

  return (
    <div className={`dashboard-surplus-viewer${selectable ? " dashboard-surplus-viewer-selectable" : ""}`}>
      <div className="dashboard-surplus-stage">
        <img
          src={activeImage}
          alt={`${title} photo ${activeIndex + 1}`}
          className={cropClassForImage?.(activeImage)}
        />
        {images.length > 1 ? (
          <>
            <button className="dashboard-surplus-arrow dashboard-surplus-arrow-left" type="button" aria-label="Previous photo" onClick={() => move(-1)}>
              &lsaquo;
            </button>
            <button className="dashboard-surplus-arrow dashboard-surplus-arrow-right" type="button" aria-label="Next photo" onClick={() => move(1)}>
              &rsaquo;
            </button>
          </>
        ) : null}
        <div className="dashboard-surplus-counter">{activeIndex + 1} of {images.length}</div>
        {selectable ? (
          <label className="dashboard-surplus-select-current">
            <input
              type="checkbox"
              checked={selectedSet.has(activeImage)}
              onChange={() => onToggleImage?.(activeImage)}
            />
            Select
          </label>
        ) : null}
      </div>
      <div className="dashboard-surplus-thumbs">
        {images.map((image, index) => (
          <button
            className={`dashboard-surplus-thumb${index === activeIndex ? " is-active" : ""}${selectedSet.has(image) ? " is-selected" : ""}`}
            type="button"
            key={`${image}-${index}`}
            onClick={() => setActiveIndex(index)}
            aria-label={`Show photo ${index + 1}`}
          >
            {selectable ? (
              <input
                type="checkbox"
                checked={selectedSet.has(image)}
                onChange={(event) => {
                  event.stopPropagation();
                  onToggleImage?.(image);
                }}
                onClick={(event) => event.stopPropagation()}
                aria-label={`Select photo ${index + 1}`}
              />
            ) : null}
            <img
              src={image}
              alt={`${title} thumbnail ${index + 1}`}
              className={cropClassForImage?.(image)}
            />
          </button>
        ))}
      </div>
    </div>
  );
}
