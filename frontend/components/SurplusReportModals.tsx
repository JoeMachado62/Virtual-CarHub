/* eslint-disable @next/next/no-img-element */
"use client";

import type { ReactNode } from "react";

import { SurplusImageGallery } from "@/components/SurplusImageGallery";

export type SurplusReportModalData = {
  vin: string;
  title: string;
  message: string;
  images: string[];
  hiddenImages: string[];
  selectedHiddenImages: string[];
  orderPrice: number;
};

type BaseProps = {
  modal: SurplusReportModalData;
  ordering: boolean;
  onClose: () => void;
  onOrder: () => void;
  cropClassForImage: (image: string) => string | undefined;
};

type AdminProps = BaseProps & {
  onToggleHiddenImage: (image: string) => void;
  onPublishHiddenImages: () => void;
};

export function SurplusUserReportModal({
  modal,
  ordering,
  onClose,
  onOrder,
  cropClassForImage,
}: BaseProps) {
  return (
    <SurplusModalShell
      modal={modal}
      ordering={ordering}
      onClose={onClose}
      onOrder={onOrder}
      className="dashboard-surplus-user-modal"
    >
      <SurplusImageGallery
        images={modal.images}
        title={modal.title}
        emptyMessage="No screened MarketCheck photos are available yet."
        cropClassForImage={cropClassForImage}
      />
    </SurplusModalShell>
  );
}

export function SurplusAdminReportModal({
  modal,
  ordering,
  onClose,
  onOrder,
  onToggleHiddenImage,
  onPublishHiddenImages,
  cropClassForImage,
}: AdminProps) {
  return (
    <SurplusModalShell
      modal={modal}
      ordering={ordering}
      onClose={onClose}
      onOrder={onOrder}
      className="dashboard-surplus-admin-modal"
    >
      <section className="dashboard-surplus-admin-layout">
        <div className="dashboard-surplus-admin-preview">
          <p className="section-eyebrow">Customer Preview</p>
          <SurplusImageGallery
            images={modal.images}
            title={modal.title}
            emptyMessage="No screened MarketCheck photos are available yet."
            cropClassForImage={cropClassForImage}
          />
        </div>
        {modal.hiddenImages.length ? (
          <div className="dashboard-surplus-admin-review">
            <div className="dashboard-surplus-review-head">
              <p className="section-eyebrow">Admin Hidden Images</p>
              <span>{modal.hiddenImages.length} hidden</span>
            </div>
            <SurplusImageGallery
              images={modal.hiddenImages}
              title={`${modal.title} hidden`}
              emptyMessage="No hidden MarketCheck photos are available."
              selectedImages={modal.selectedHiddenImages}
              onToggleImage={onToggleHiddenImage}
              cropClassForImage={cropClassForImage}
              mode="select-grid"
            />
            <button
              className="button ghost dashboard-surplus-publish-button"
              type="button"
              onClick={onPublishHiddenImages}
              disabled={!modal.selectedHiddenImages.length}
            >
              Publish Selected
            </button>
          </div>
        ) : null}
      </section>
    </SurplusModalShell>
  );
}

type ShellProps = Omit<BaseProps, "cropClassForImage"> & {
  className: string;
  children: ReactNode;
};

function SurplusModalShell({
  modal,
  ordering,
  onClose,
  onOrder,
  className,
  children,
}: ShellProps) {
  return (
    <div className="dashboard-cr-modal-overlay" onClick={onClose}>
      <div
        className={`card dashboard-surplus-modal ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`surplus-modal-title-${modal.vin}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="dashboard-surplus-modal-scroll">
          <div className="dashboard-surplus-modal-copy">
            <p className="section-eyebrow" style={{ marginBottom: 8 }}>
              Surplus Inventory Inspection
            </p>
            <h3 id={`surplus-modal-title-${modal.vin}`}>{modal.title}</h3>
            <p>{modal.message}</p>
          </div>
          {children}
        </div>
        <div className="dashboard-surplus-modal-actions">
          <button className="button ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="button" type="button" onClick={onOrder} disabled={ordering}>
            {ordering ? "Ordering..." : `ORDER REPORT $${modal.orderPrice}`}
          </button>
        </div>
      </div>
    </div>
  );
}
