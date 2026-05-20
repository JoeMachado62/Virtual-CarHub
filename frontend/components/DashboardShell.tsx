/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { DannyChat } from "@/components/DannyChat";
import { DealTracker } from "@/components/DealTracker";
import { QuickMatchForm } from "@/components/QuickMatchForm";
import { Recommendation, RecommendationCards } from "@/components/RecommendationCards";
import { apiFetch } from "@/lib/api";
import { AuthState, canAccessConditionReports, clearAuthState, isAdminUser, loadValidAuthState, saveAuthState } from "@/lib/auth";
import { toPublicSourceLabel } from "@/lib/sourceLabels";
import { maskVin } from "@/lib/vin";

type DisplayMode = "MARKETING" | "INSPECTION_PENDING" | "INSPECTION_REPORT";
type InspectionStatus = "NOT_STARTED" | "PENDING" | "INGESTED" | "NORMALIZED" | "VERIFIED" | "FAILED";

type DealSummary = {
  id: string;
  stage: string;
  funding_state: string;
  condition_report_eligible: boolean;
  condition_report_eligibility_reason: string | null;
  assigned_agent: string | null;
  human_checkpoint_required: boolean;
  selected_vin: string | null;
  delivered_at: string | null;
  closed_at: string | null;
};

type GarageItem = {
  id: string;
  vin: string;
  public_slug?: string | null;
  status: string;
  source: string;
  added_at: string | null;
  updated_at: string | null;
  acquisition_started_at: string | null;
  deal_stage: string;
  display_mode: DisplayMode;
  inspection_status: InspectionStatus;
  has_inspection_report: boolean;
  cr_request_status?: string | null;
  vehicle: {
    year?: number | null;
    make?: string | null;
    model?: string | null;
    trim?: string | null;
    price_asking?: number | null;
    odometer?: number | null;
    location_state?: string | null;
    location_zip?: string | null;
    source_type?: string | null;
    thumbnail?: string | null;
  };
};

type NotificationItem = {
  id: string;
  message: string;
  channel?: string;
  is_read?: boolean;
  created_at?: string | null;
};

const FALLBACK_IMAGE = "/assets/images/portfolio/01.webp";

type AuthView = "login" | "register" | "onboarding" | "forgot-password";
type CrRequestModalState = {
  vin: string;
  title: string;
  imageUrl: string;
  alreadyAvailable: boolean;
};

type SurplusReportModalState = {
  vin: string;
  title: string;
  message: string;
  images: string[];
  hiddenImages: string[];
  selectedHiddenImages: string[];
  orderPrice: number;
};

export function DashboardShell({ requestedVin }: { requestedVin?: string | null }) {
  const searchParams = useSearchParams();
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [deal, setDeal] = useState<DealSummary | null>(null);
  const [isPreapproved, setIsPreapproved] = useState(false);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [garageItems, setGarageItems] = useState<GarageItem[]>([]);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [garageMessage, setGarageMessage] = useState<string | null>(null);
  const [garageError, setGarageError] = useState<string | null>(null);
  const [garageActionVin, setGarageActionVin] = useState<string | null>(null);
  const [markingNotificationsRead, setMarkingNotificationsRead] = useState(false);
  const [pendingReportVins, setPendingReportVins] = useState<Set<string>>(new Set());
  const [crRequestModal, setCrRequestModal] = useState<CrRequestModalState | null>(null);
  const [surplusReportModal, setSurplusReportModal] = useState<SurplusReportModalState | null>(null);
  const [orderingSurplusReport, setOrderingSurplusReport] = useState(false);
  const [profileBfv, setProfileBfv] = useState<Record<string, unknown> | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Registration fields
  const [authView, setAuthView] = useState<AuthView>("login");
  const [regFirstName, setRegFirstName] = useState("");
  const [regLastName, setRegLastName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPhone, setRegPhone] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirmPassword, setRegConfirmPassword] = useState("");
  const [registering, setRegistering] = useState(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Forgot password fields
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotSubmitting, setForgotSubmitting] = useState(false);
  const [forgotMessage, setForgotMessage] = useState<string | null>(null);
  const [forgotError, setForgotError] = useState<string | null>(null);

  const isAuthenticated = useMemo(() => Boolean(auth?.accessToken), [auth]);
  const normalizedRequestedVin = requestedVin?.trim().toUpperCase() || null;
  const emailLoginToken = searchParams.get("email_login_token");

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      const saved = await loadValidAuthState();
      if (cancelled) return;
      if (saved) {
        setAuth(saved);
        if (saved.email) setEmail(saved.email);
      }
      setAuthReady(true);
    }

    void restoreSession();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!authReady || !emailLoginToken) return;
    if (auth?.accessToken) {
      if (typeof window !== "undefined") {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.delete("email_login_token");
        window.history.replaceState({}, "", `${nextUrl.pathname}${nextUrl.search}`);
      }
      return;
    }

    let cancelled = false;

    async function consumeEmailLogin() {
      setLoggingIn(true);
      setLoginError(null);

      const response = await apiFetch<{
        user_id: string;
        email?: string;
        access_token: string;
        refresh_token: string;
        token_type: string;
      }>("/auth/email-login", {
        method: "POST",
        body: JSON.stringify({ token: emailLoginToken }),
      });

      if (cancelled) return;

      if (response.status !== "ok") {
        setDashboardError(response.error?.message || "Unable to open your garage from the email link.");
        setLoggingIn(false);
        return;
      }

      const nextAuth: AuthState = {
        userId: response.data.user_id,
        email: response.data.email || "",
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token,
      };
      saveAuthState(nextAuth);
      setAuth(nextAuth);
      if (response.data.email) setEmail(response.data.email);
      if (typeof window !== "undefined") {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.delete("email_login_token");
        window.history.replaceState({}, "", `${nextUrl.pathname}${nextUrl.search}`);
      }
      setLoggingIn(false);
    }

    void consumeEmailLogin();

    return () => {
      cancelled = true;
    };
  }, [auth?.accessToken, authReady, emailLoginToken]);

  function resetSession(message?: string) {
    clearAuthState();
    setAuth(null);
    setDeal(null);
    setRecommendations([]);
    setNotifications([]);
    setGarageItems([]);
    setPendingReportVins(new Set());
    setGarageMessage(null);
    setGarageActionVin(null);
    setLoading(false);
    if (message) {
      setDashboardError(message);
      setGarageError(message);
    }
  }

  function isUnauthorized(response: { error: { code: string; message: string } | null }) {
    return response.error?.code === "HTTP_401";
  }

  async function login() {
    setLoggingIn(true);
    setLoginError(null);
    const response = await apiFetch<{
      user_id: string;
      access_token: string;
      refresh_token: string;
      token_type: string;
    }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password })
      }
    );

    if (response.status === "ok") {
      const nextAuth: AuthState = {
        userId: response.data.user_id,
        email,
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token
      };
      setAuth(nextAuth);
      saveAuthState(nextAuth);
    } else {
      setLoginError(response.error?.message || "Unable to sign in.");
    }
    setLoggingIn(false);
  }

  async function register() {
    if (regPassword !== regConfirmPassword) {
      setRegisterError("Passwords do not match.");
      return;
    }
    if (regPassword.length < 8) {
      setRegisterError("Password must be at least 8 characters.");
      return;
    }
    if (!regFirstName.trim() || !regLastName.trim()) {
      setRegisterError("First and last name are required.");
      return;
    }

    setRegistering(true);
    setRegisterError(null);
    const response = await apiFetch<{
      user_id: string;
      access_token: string;
      refresh_token: string;
      token_type: string;
      ghl_contact_id: string | null;
      is_new_user: boolean;
    }>(
      "/auth/register",
      {
        method: "POST",
        body: JSON.stringify({
          email: regEmail,
          password: regPassword,
          first_name: regFirstName,
          last_name: regLastName,
          phone: regPhone || undefined
        })
      }
    );

    if (response.status === "ok") {
      const nextAuth: AuthState = {
        userId: response.data.user_id,
        email: regEmail,
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token
      };
      saveAuthState(nextAuth);
      // Show onboarding choice before entering dashboard
      setShowOnboarding(true);
      setAuth(nextAuth);
    } else {
      setRegisterError(response.error?.message || "Unable to create account.");
    }
    setRegistering(false);
  }

  async function forgotPassword() {
    if (!forgotEmail.trim()) {
      setForgotError("Please enter your email address.");
      return;
    }
    setForgotSubmitting(true);
    setForgotError(null);
    setForgotMessage(null);
    const response = await apiFetch<{ message: string }>(
      "/auth/forgot-password",
      {
        method: "POST",
        body: JSON.stringify({ email: forgotEmail })
      }
    );
    if (response.status === "ok") {
      setForgotMessage(response.data.message);
    } else {
      setForgotError(response.error?.message || "Something went wrong. Please try again.");
    }
    setForgotSubmitting(false);
  }

  async function refreshData() {
    if (!auth?.accessToken) return;

    setLoading(true);
    setDashboardError(null);
    setGarageError(null);

    const [dealResponse, recs, notes, garage, accountStatus, profileResponse] = await Promise.all([
      apiFetch<DealSummary>("/me/deal", {}, auth.accessToken),
      apiFetch<Recommendation[]>("/me/recommendations/refresh", { method: "POST" }, auth.accessToken),
      apiFetch<NotificationItem[]>("/me/notifications", {}, auth.accessToken),
      apiFetch<GarageItem[]>("/me/garage", {}, auth.accessToken),
      apiFetch<{ is_preapproved: boolean }>("/me/account-status", {}, auth.accessToken),
      apiFetch<{ first_name: string | null; last_name: string | null; bfv_json: Record<string, unknown> | null }>("/me/profile", {}, auth.accessToken)
    ]);

    if ([dealResponse, recs, notes, garage].some(isUnauthorized)) {
      resetSession("Your session expired. Sign in again.");
      return;
    }

    if (dealResponse.status === "ok") {
      setDeal(dealResponse.data);
    } else {
      setDashboardError(dealResponse.error?.message || "Unable to load deal state.");
    }

    if (recs.status === "ok") {
      setRecommendations(recs.data || []);
    } else {
      setDashboardError((current) => current || recs.error?.message || "Unable to load recommendations.");
    }

    if (notes.status === "ok") {
      setNotifications(notes.data || []);
    } else {
      setDashboardError((current) => current || notes.error?.message || "Unable to load notifications.");
    }

    if (accountStatus.status === "ok" && accountStatus.data) {
      setIsPreapproved(Boolean(accountStatus.data.is_preapproved));
    } else {
      setIsPreapproved(false);
    }

    if (profileResponse.status === "ok") {
      if (profileResponse.data?.bfv_json) {
        setProfileBfv(profileResponse.data.bfv_json);
      }
      const fn = profileResponse.data?.first_name?.trim() || "";
      const ln = profileResponse.data?.last_name?.trim() || "";
      const full = [fn, ln].filter(Boolean).join(" ");
      setDisplayName(full);
    }

    if (garage.status === "ok") {
      const items = garage.data || [];
      setGarageItems(items);
      // Seed pending status from the server so report requests survive reloads.
      const serverPendingVins = new Set(
        items.filter((item) => item.cr_request_status === "pending").map((item) => item.vin),
      );
      const vinsWithReports = new Set(items.filter(item => item.has_inspection_report).map(item => item.vin));
      setPendingReportVins(prev => {
        const updated = new Set(prev);
        serverPendingVins.forEach((vin) => updated.add(vin));
        vinsWithReports.forEach(vin => updated.delete(vin));
        return updated;
      });
    } else {
      setGarageItems([]);
      setGarageError(garage.error?.message || "Unable to load garage.");
    }

    setLoading(false);
  }

  async function refreshGarageStatus(options?: { silent?: boolean }) {
    if (!auth?.accessToken) return;

    if (!options?.silent) {
      setGarageError(null);
    }

    const [garage, notes] = await Promise.all([
      apiFetch<GarageItem[]>("/me/garage", {}, auth.accessToken),
      apiFetch<NotificationItem[]>("/me/notifications", {}, auth.accessToken),
    ]);

    if ([garage, notes].some(isUnauthorized)) {
      resetSession("Your session expired. Sign in again.");
      return;
    }

    if (notes.status === "ok") {
      setNotifications(notes.data || []);
    }

    if (garage.status !== "ok") {
      setGarageError(garage.error?.message || "Unable to load garage.");
      return;
    }

    const items = garage.data || [];
    setGarageItems(items);

    // Seed pendingReportVins from backend cr_request_status so the
    // "CR Pending" state survives page reloads.
    const serverPendingVins = new Set(
      items.filter((item) => item.cr_request_status === "pending").map((item) => item.vin),
    );
    const vinsWithReports = new Set(items.filter((item) => item.has_inspection_report).map((item) => item.vin));
    const completedVins = [...pendingReportVins].filter((vin) => vinsWithReports.has(vin));

    setPendingReportVins((prev) => {
      const next = new Set(prev);
      // Add any server-side pending VINs the client didn't know about
      serverPendingVins.forEach((vin) => next.add(vin));
      // Remove VINs that now have reports
      completedVins.forEach((vin) => next.delete(vin));
      return next;
    });

    if (completedVins.length) {
      const completedTitles = completedVins
        .map((vin) => items.find((item) => item.vin === vin))
        .filter((item): item is GarageItem => Boolean(item))
        .map((item) => garageTitle(item));
      setGarageMessage(
        completedTitles.length === 1
          ? `${completedTitles[0]} inspection report is ready.`
          : `${completedTitles.length} inspection reports are now ready.`,
      );
    }
  }

  useEffect(() => {
    if (!authReady) return;
    void refreshData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth?.accessToken, authReady]);

  useEffect(() => {
    if (!auth?.accessToken || pendingReportVins.size === 0) return;

    const intervalId = window.setInterval(() => {
      void refreshGarageStatus({ silent: true });
    }, 15000);

    return () => {
      window.clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth?.accessToken, pendingReportVins.size]);

  async function selectVehicle(vin: string) {
    if (!auth?.accessToken) return;
    const response = await apiFetch(`/me/recommendations/${vin}/select`, { method: "POST" }, auth.accessToken);
    if (response.status !== "ok") {
      setDashboardError(response.error?.message || "Unable to select vehicle.");
      return;
    }
    setGarageMessage("Vehicle selected and added to My Garage.");
    await refreshData();
  }

  async function favoriteVehicle(vin: string) {
    if (!auth?.accessToken) return;
    const response = await apiFetch(`/me/recommendations/${vin}/favorite`, { method: "POST" }, auth.accessToken);
    if (response.status !== "ok") {
      setDashboardError(response.error?.message || "Unable to favorite vehicle.");
      return;
    }
    await refreshData();
  }

  async function initiateReturn() {
    if (!auth?.accessToken) return;
    const response = await apiFetch(
      "/me/return/initiate",
      {
        method: "POST",
        body: JSON.stringify({ reason: "Preference changed", buyer_transport_responsibility: true })
      },
      auth.accessToken
    );
    if (response.status !== "ok") {
      setDashboardError(response.error?.message || "Unable to initiate return.");
      return;
    }
    await refreshData();
  }

  async function markNotificationsRead() {
    if (!auth?.accessToken) return;
    const unreadIds = notifications.filter((note) => !note.is_read).map((note) => note.id);
    if (!unreadIds.length) return;

    setMarkingNotificationsRead(true);
    const response = await apiFetch(
      "/me/notifications/mark-read",
      {
        method: "POST",
        body: JSON.stringify({ ids: unreadIds }),
      },
      auth.accessToken,
    );

    if (response.status !== "ok") {
      setDashboardError(response.error?.message || "Unable to mark notifications read.");
      setMarkingNotificationsRead(false);
      return;
    }

    setNotifications((current) => current.filter((note) => !unreadIds.includes(note.id)));
    setMarkingNotificationsRead(false);
  }

  async function requestConditionReport(vin: string) {
    if (!auth?.accessToken) return;
    if (!canAccessConditionReports(auth, { isPreapproved, crEligible: deal?.condition_report_eligible })) {
      setGarageError("Condition report requests require a pre-qualified buyer account.");
      return;
    }

    const garageItem = garageItems.find((item) => item.vin === vin);
    if (garageItem && isSurplusGarageItem(garageItem)) {
      await previewSurplusConditionReport(garageItem);
      return;
    }

    setGarageActionVin(vin);
    setGarageError(null);
    setGarageMessage(null);
    const response = await apiFetch<{
      message?: string;
      already_available?: boolean;
      status?: string;
      request_id?: string;
      deduplicated?: boolean;
    }>(
      `/me/vehicles/${encodeURIComponent(vin)}/condition-report-request`,
      { method: "POST" },
      auth.accessToken
    );
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to request inspection report.");
      setGarageActionVin(null);
      return;
    }

    const ready = Boolean(response.data.already_available || response.data.status === "available");
    if (!ready) {
      setPendingReportVins((prev) => {
        const next = new Set(prev);
        next.add(vin);
        return next;
      });
    }
    setGarageMessage(
      response.data.message ||
        (ready
          ? "Inspection report is ready."
          : "Report requested. My Garage will update when the inspection report is ready."),
    );
    setCrRequestModal({
      vin,
      title: garageItem ? garageTitle(garageItem) : vin,
      imageUrl: garageItem?.vehicle.thumbnail || FALLBACK_IMAGE,
      alreadyAvailable: ready,
    });
    await refreshGarageStatus({ silent: true });
    setGarageActionVin(null);
  }

  async function previewSurplusConditionReport(item: GarageItem) {
    if (!auth?.accessToken) return;
    setGarageActionVin(item.vin);
    setGarageError(null);
    setGarageMessage(null);
    const response = await apiFetch<{
      title?: string;
      message: string;
      images: string[];
      hidden_images?: string[];
      order_price?: number;
    }>(
      `/me/vehicles/${encodeURIComponent(item.vin)}/surplus-condition-report-preview`,
      { method: "POST" },
      auth.accessToken,
    );
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to prepare surplus inspection report options.");
      setGarageActionVin(null);
      return;
    }

    setSurplusReportModal({
      vin: item.vin,
      title: response.data.title || garageTitle(item),
      message: response.data.message,
      images: response.data.images || [],
      hiddenImages: response.data.hidden_images || [],
      selectedHiddenImages: [],
      orderPrice: response.data.order_price || 99,
    });
    setGarageActionVin(null);
  }

  function toggleHiddenSurplusImage(image: string) {
    setSurplusReportModal((current) => {
      if (!current) return current;
      const selected = new Set(current.selectedHiddenImages);
      if (selected.has(image)) selected.delete(image);
      else selected.add(image);
      return { ...current, selectedHiddenImages: Array.from(selected) };
    });
  }

  async function publishHiddenSurplusImages() {
    if (!auth?.accessToken || !surplusReportModal || !isAdminUser(auth) || !surplusReportModal.selectedHiddenImages.length) return;
    setGarageError(null);
    const selected = surplusReportModal.selectedHiddenImages;
    const response = await apiFetch<{ published_images?: string[]; published_count?: number }>(
      `/me/vehicles/${encodeURIComponent(surplusReportModal.vin)}/surplus-condition-report-images/publish`,
      {
        method: "POST",
        body: JSON.stringify({ image_urls: selected }),
      },
      auth.accessToken,
    );
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to publish selected images.");
      return;
    }
    const published = response.data.published_images || selected;
    setSurplusReportModal((current) => {
      if (!current) return current;
      const publishedSet = new Set(published);
      return {
        ...current,
        images: Array.from(new Set([...current.images, ...published])),
        hiddenImages: current.hiddenImages.filter((image) => !publishedSet.has(image)),
        selectedHiddenImages: [],
      };
    });
    setGarageMessage(`${response.data.published_count || published.length} image${(response.data.published_count || published.length) === 1 ? "" : "s"} published to the report gallery.`);
  }

  async function orderSurplusConditionReport() {
    if (!auth?.accessToken || !surplusReportModal) return;
    setOrderingSurplusReport(true);
    setGarageError(null);
    const response = await apiFetch<{ message?: string }>(
      `/me/vehicles/${encodeURIComponent(surplusReportModal.vin)}/surplus-condition-report-order`,
      { method: "POST" },
      auth.accessToken,
    );
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to order the surplus inspection report.");
      setOrderingSurplusReport(false);
      return;
    }

    setPendingReportVins((prev) => {
      const next = new Set(prev);
      next.add(surplusReportModal.vin);
      return next;
    });
    setGarageMessage(response.data.message || "Surplus inspection report ordered. My Garage will update when it is ready.");
    setSurplusReportModal(null);
    await refreshGarageStatus({ silent: true });
    setOrderingSurplusReport(false);
  }

  async function startGarageAcquisition(vin: string) {
    if (!auth?.accessToken) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageMessage(null);
    const response = await apiFetch(`/me/garage/${vin}/acquire`, { method: "POST" }, auth.accessToken);
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to start purchase.");
      setGarageActionVin(null);
      return;
    }
    setGarageMessage("Purchase started. Returning the latest garage state.");
    await refreshData();
    setGarageActionVin(null);
  }

  async function removeFromGarage(vin: string) {
    if (!auth?.accessToken) return;
    setGarageActionVin(vin);
    setGarageError(null);
    setGarageMessage(null);
    const response = await apiFetch(`/me/garage/${vin}`, { method: "DELETE" }, auth.accessToken);
    if (response.status !== "ok") {
      setGarageError(response.error?.message || "Unable to remove vehicle from garage.");
      setGarageActionVin(null);
      return;
    }
    setGarageItems((current) => current.filter((item) => item.vin !== vin));
    setGarageMessage("Vehicle removed from My Garage.");
    setGarageActionVin(null);
  }

  const spotlightVin = normalizedRequestedVin || deal?.selected_vin || garageItems[0]?.vin || null;
  const spotlightItem = garageItems.find((item) => item.vin === spotlightVin) || garageItems[0] || null;
  const selectedGarageItem = deal?.selected_vin ? garageItems.find((item) => item.vin === deal.selected_vin) : null;
  const auctionGarageCount = garageItems.filter(
    (item) => item.vehicle.source_type === "ove" || item.vehicle.source_type === "auction"
  ).length;
  const unreadNotifications = notifications.filter((note) => !note.is_read);
  const renderGarageReportAction = (item: GarageItem) => {
    const itemActionLoading = garageActionVin === item.vin;
    const reportPending = isReportPending(item, pendingReportVins);
    const reportEligible = canAccessConditionReports(auth, { isPreapproved, crEligible: deal?.condition_report_eligible });

    if (item.has_inspection_report) {
      return (
        <Link className="button ghost-mint" href={`/vinventory/${encodeURIComponent(item.public_slug || item.vin)}/condition-report`}>
          Inspection Report Ready
        </Link>
      );
    }

    if (reportPending) {
      return (
        <button className="button ghost-mint" disabled>
          Report Requested
        </button>
      );
    }

    if (!canRequestReportForGarageItem(item)) return null;

    if (!reportEligible) {
      return (
        <button
          className="button ghost-mint"
          onClick={() => setGarageError("Condition report requests require a pre-qualified buyer account.")}
        >
          Prequalify to Request
        </button>
      );
    }

    return (
      <button
        className="button ghost-mint"
        onClick={() => requestConditionReport(item.vin)}
        disabled={itemActionLoading}
      >
        {itemActionLoading ? "Requesting..." : item.cr_request_status === "terminal" ? "Retry Report" : "Report Request"}
      </button>
    );
  };

  if (!authReady) {
    return (
      <div className="card dashboard-login-card">
        <h2>Client Dashboard Login</h2>
        <p>Checking saved session...</p>
      </div>
    );
  }

  if (isAuthenticated && showOnboarding) {
    return (
      <div className="card dashboard-login-card dashboard-onboarding-card">
        <div className="dashboard-onboarding-header">
          <span className="section-eyebrow">Welcome to My Garage</span>
          <h2>You&apos;re all set, {regFirstName || "there"}!</h2>
          <p>Your account has been created. Let Danny help find the right wholesale deal, or jump straight into browsing.</p>
        </div>

        <div className="dashboard-onboarding-choices">
          <div className="dashboard-onboarding-option dashboard-onboarding-option-primary">
            <h3>Danny&apos;s Onboarding</h3>
            <p>Answer a few quick questions about body type, budget, and priorities. Danny will start matching you with better-fit vehicles right away.</p>
            <p className="badge">Takes about 60 seconds</p>
            <button
              className="button"
              onClick={() => {
                setShowOnboarding(false);
                setAuthView("onboarding");
              }}
            >
              Start Onboarding
            </button>
          </div>

          <div className="dashboard-onboarding-option">
            <h3>Skip &amp; Browse</h3>
            <p>Head straight to the inventory and explore on your own. You can always complete the onboarding later from your dashboard.</p>
            <button
              className="button ghost"
              onClick={() => {
                setShowOnboarding(false);
              }}
            >
              Browse Inventory
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="card dashboard-login-card">
        <div className="dashboard-auth-tabs">
          <button
            className={`dashboard-auth-tab${authView === "login" ? " active" : ""}`}
            onClick={() => { setAuthView("login"); setLoginError(null); }}
          >
            Sign In
          </button>
          <button
            className={`dashboard-auth-tab${authView === "register" ? " active" : ""}`}
            onClick={() => { setAuthView("register"); setRegisterError(null); }}
          >
            Create Account
          </button>
        </div>

        {authView === "forgot-password" ? (
          <>
            <h2>Reset Your Password</h2>
            <p>Enter the email address you used to create your account and we&apos;ll send you a link to reset your password.</p>
            <label>
              Email
              <input
                className="input"
                type="email"
                value={forgotEmail}
                onChange={(e) => setForgotEmail(e.target.value)}
              />
            </label>
            {forgotError ? <p className="dashboard-error">{forgotError}</p> : null}
            {forgotMessage ? <p className="dashboard-success">{forgotMessage}</p> : null}
            <button className="button" disabled={forgotSubmitting} onClick={forgotPassword}>
              {forgotSubmitting ? "Sending..." : "Send Reset Link"}
            </button>
            <p className="dashboard-auth-switch">
              <button className="link-button" onClick={() => { setAuthView("login"); setForgotError(null); setForgotMessage(null); }}>
                Back to Sign In
              </button>
            </p>
          </>
        ) : authView === "login" ? (
          <>
            <h2>Welcome Back</h2>
            <p>Sign in to access My Garage, saved vehicles, and your deal workspace.</p>
            <label>
              Email
              <input className="input" value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
            <label>
              Password
              <input
                className="input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {loginError ? <p className="dashboard-error">{loginError}</p> : null}
            <button className="button" disabled={loggingIn} onClick={login}>
              {loggingIn ? "Signing in..." : "Sign In"}
            </button>
            <p className="dashboard-auth-switch">
              <button className="link-button" onClick={() => { setAuthView("forgot-password"); setForgotEmail(email); }}>
                Forgot your password?
              </button>
            </p>
            <p className="dashboard-auth-switch">
              Don&apos;t have an account?{" "}
              <button className="link-button" onClick={() => setAuthView("register")}>
                Create one now
              </button>
            </p>
          </>
        ) : (
          <>
            <h2>Create Your Garage Account</h2>
            <p>Set up your account to save vehicles, track deals, and get personalized recommendations from Danny.</p>
            <div className="grid two">
              <label>
                First Name <span className="required">*</span>
                <input className="input" value={regFirstName} onChange={(e) => setRegFirstName(e.target.value)} />
              </label>
              <label>
                Last Name <span className="required">*</span>
                <input className="input" value={regLastName} onChange={(e) => setRegLastName(e.target.value)} />
              </label>
            </div>
            <label>
              Email <span className="required">*</span>
              <input className="input" type="email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} />
            </label>
            <label>
              Phone <span className="muted-copy">(optional)</span>
              <input className="input" type="tel" value={regPhone} onChange={(e) => setRegPhone(e.target.value)} placeholder="(555) 555-1234" />
            </label>
            <label>
              Password <span className="required">*</span>
              <input className="input" type="password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} placeholder="At least 8 characters" />
            </label>
            <label>
              Confirm Password <span className="required">*</span>
              <input className="input" type="password" value={regConfirmPassword} onChange={(e) => setRegConfirmPassword(e.target.value)} />
            </label>
            {registerError ? <p className="dashboard-error">{registerError}</p> : null}
            <button className="button" disabled={registering} onClick={register}>
              {registering ? "Creating account..." : "Create Account"}
            </button>
            <p className="dashboard-auth-switch">
              Already have an account?{" "}
              <button className="link-button" onClick={() => setAuthView("login")}>
                Sign in
              </button>
            </p>
          </>
        )}
      </div>
    );
  }

  const accessToken = auth?.accessToken ?? "";

  return (
    <div className="dashboard-shell">
      <section className="section-shell page-hero compact">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
          <p className="section-eyebrow">My Garage</p>
          <p className="dashboard-greeting">Hello: {displayName || auth?.email || ""}</p>
        </div>
        <h1>Saved vehicles, inspection reports, and purchase status in one place.</h1>
      </section>

      {authView === "onboarding" ? (
        <section className="card dashboard-onboarding-banner">
          <div className="dashboard-onboarding-header">
            <span className="section-eyebrow">Danny&apos;s Onboarding</span>
            <h2>Let&apos;s find your ideal vehicle</h2>
            <p>Fill out Quick Match below, and Danny will start matching you with vehicles that fit your budget and priorities.</p>
          </div>
          <QuickMatchForm
            accessToken={accessToken}
            initialProfile={profileBfv ?? undefined}
            onCompleted={async () => {
              setAuthView("login");
              await refreshData();
            }}
          />
          <div style={{ textAlign: "center", marginTop: "0.5rem" }}>
            <button className="link-button" onClick={() => setAuthView("login")}>
              Skip for now — I&apos;ll browse on my own
            </button>
          </div>
        </section>
      ) : null}

      <section className="card dashboard-overview">
        <div className="dashboard-overview-head">
          <div className="dashboard-overview-copy">
            <p className="section-eyebrow">Deal Workspace</p>
            <h2>Track your buying journey, keep saved cars organized, and move the right vehicle forward.</h2>
            <p className="muted-copy">
              My Garage keeps saved vehicles, inspection reports, messages, and purchase status in one place.
            </p>
          </div>
          <div className="dashboard-toolbar">
            <button className="button ghost" onClick={refreshData} disabled={loading}>
              {loading ? "Refreshing..." : "Refresh"}
            </button>
            <button
              className="button ghost"
              onClick={() => {
                resetSession();
              }}
            >
              Sign Out
            </button>
          </div>
        </div>

        <div className="dashboard-kpis">
          <article className="metric">
            <strong>{garageItems.length}</strong>
            <span>Saved in garage</span>
          </article>
          <article className="metric">
            <strong>{auctionGarageCount}</strong>
            <span>Auction units</span>
          </article>
          <article className="metric">
            <strong>{deal?.stage ? deal.stage.replaceAll("_", " ") : "Loading"}</strong>
            <span>Current deal stage</span>
          </article>
          <article className="metric">
            <strong>{selectedGarageItem ? garageTitle(selectedGarageItem) : "None selected"}</strong>
            <span>Current purchase target</span>
          </article>
        </div>

        {dashboardError ? <p className="dashboard-error">{dashboardError}</p> : null}
        {deal?.human_checkpoint_required ? (
          <p className="dashboard-warning">A human checkpoint is required before the deal can advance automatically.</p>
        ) : null}
        {deal && !deal.condition_report_eligible ? (
          <p className="dashboard-muted-note">
            Inspection reports become available later in the buying process. {deal.condition_report_eligibility_reason}
          </p>
        ) : null}
        {normalizedRequestedVin && !garageItems.some((item) => item.vin === normalizedRequestedVin) ? (
          <p className="dashboard-warning">
            Requested VIN {maskVin(normalizedRequestedVin, isAdminUser(auth) || isPreapproved)} is not currently in My Garage. Showing the latest saved vehicle instead.
          </p>
        ) : null}
      </section>

      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <h2 style={{ margin: 0 }}>Purchase Status</h2>
          {deal?.assigned_agent ? <span className="badge">Assigned agent: {deal.assigned_agent}</span> : null}
        </div>
        <DealTracker stage={deal?.stage || "LEAD"} />
      </section>

      <section className="dashboard-garage-layout">
        <section className="card inventory-garage">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0 }}>My Garage</h2>
              <p className="dashboard-muted-note" style={{ marginBottom: 0 }}>
                Saved wholesale and inventory vehicles stay connected to your buying journey.
              </p>
            </div>
            <span className="badge">{garageItems.length} saved</span>
          </div>
          {garageError ? <p className="dashboard-error">{garageError}</p> : null}
          {garageMessage ? <p className="dashboard-success">{garageMessage}</p> : null}
          {!garageItems.length ? (
            <div className="dashboard-empty-state">
              <p style={{ margin: 0 }}>No vehicles saved yet.</p>
              <Link className="button" href="/vinventory">
                Browse Inventory
              </Link>
            </div>
          ) : (
            <div className="inventory-garage-grid">
              {garageItems.map((item) => {
                const isSpotlight = item.vin === spotlightItem?.vin;
                const isSelected = item.vin === deal?.selected_vin;
                const itemActionLoading = garageActionVin === item.vin;
                const isSold = item.status === "sold";

                return (
                  <article
                    key={item.id}
                    className={`inventory-garage-item dashboard-garage-item${isSpotlight ? " is-spotlight" : ""}${isSold ? " is-sold" : ""}`}
                  >
                    {isSold ? (
                      <div className="dashboard-garage-sold-banner">
                        <span className="dashboard-garage-sold-text">SOLD</span>
                      </div>
                    ) : null}
                    <div className="dashboard-garage-item-copy">
                      <div className="dashboard-garage-item-head">
                        <strong className="dashboard-garage-title">{garageTitle(item)}</strong>
                        <div className="dashboard-garage-badges">
                          {isSelected ? <span className="badge">Selected</span> : null}
                          {isSpotlight ? <span className="badge">Focused</span> : null}
                          {isSold ? (
                            <span className="badge badge-sold">Sold</span>
                          ) : (
                            <span className="badge">{statusLabel(item.status)}</span>
                          )}
                        </div>
                      </div>
                      <p className="dashboard-garage-price">
                        {formatMoney(item.vehicle.price_asking)} | {garageLocation(item)}
                      </p>
                      <p className="dashboard-garage-meta">VIN: {maskVin(item.vin, isAdminUser(auth) || isPreapproved)}</p>
                      <p className="dashboard-garage-meta">
                        {displayModeLabel(item.display_mode)} | {inspectionStatusLabel(item.inspection_status)}
                      </p>
                      <p className="dashboard-garage-meta">
                        Added {formatDate(item.added_at)} | Updated {formatDate(item.updated_at)}
                      </p>
                    </div>
                    <div className="inventory-actions dashboard-garage-actions">
                      {!isSpotlight ? (
                        <Link className="button ghost-accent" href={`/dashboard?vin=${encodeURIComponent(item.vin)}`}>
                          Focus
                        </Link>
                      ) : null}
                      <Link className="button secondary" href={`/vinventory/${encodeURIComponent(item.public_slug || item.vin)}`}>
                        View Details
                      </Link>
                      {isSold ? (
                        <Link
                          className="button ghost-accent"
                          href={`/inventory?${item.vehicle.year ? `year=${item.vehicle.year}&` : ""}${item.vehicle.make ? `make=${encodeURIComponent(item.vehicle.make)}&` : ""}${item.vehicle.model ? `model=${encodeURIComponent(item.vehicle.model)}` : ""}`}
                        >
                          Find Similar Vehicles
                        </Link>
                      ) : (
                        <>
                          {renderGarageReportAction(item)}
                          <button className="button" onClick={() => startGarageAcquisition(item.vin)} disabled={itemActionLoading}>
                            {itemActionLoading ? "Starting..." : "Start Purchase"}
                          </button>
                        </>
                      )}
                      <button className="button ghost-danger" onClick={() => removeFromGarage(item.vin)} disabled={itemActionLoading}>
                        Remove
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        <aside className="card dashboard-spotlight">
          <div className="dashboard-spotlight-head">
            <div>
              <p className="section-eyebrow">Garage Spotlight</p>
              <h2>{spotlightItem ? garageTitle(spotlightItem) : "Waiting for a saved vehicle"}</h2>
            </div>
            {spotlightItem?.vin === deal?.selected_vin ? <span className="badge">Primary purchase target</span> : null}
          </div>

          {spotlightItem ? (
            <>
              <div className={`dashboard-spotlight-media${spotlightItem.status === "sold" ? " is-sold" : ""}`}>
                <img
                  src={spotlightItem.vehicle.thumbnail || FALLBACK_IMAGE}
                  alt={garageTitle(spotlightItem)}
                />
                {spotlightItem.status === "sold" ? (
                  <div className="dashboard-sold-overlay">
                    <span className="dashboard-sold-overlay-text">SOLD</span>
                  </div>
                ) : null}
              </div>
              <div className="dashboard-spotlight-facts">
                <div className="vinv-modal-data-row">
                  <span>Deal stage</span>
                  <strong>{spotlightItem.deal_stage.replaceAll("_", " ")}</strong>
                </div>
                <div className="vinv-modal-data-row">
                  <span>Status</span>
                  <strong>{statusLabel(spotlightItem.status)}</strong>
                </div>
                <div className="vinv-modal-data-row">
                  <span>Inspection</span>
                  <strong>{inspectionStatusLabel(spotlightItem.inspection_status)}</strong>
                </div>
                <div className="vinv-modal-data-row">
                  <span>Source</span>
                  <strong>{sourceLabel(spotlightItem.vehicle.source_type)}</strong>
                </div>
                <div className="vinv-modal-data-row">
                  <span>Price</span>
                  <strong>{formatMoney(spotlightItem.vehicle.price_asking)}</strong>
                </div>
                <div className="vinv-modal-data-row">
                  <span>Odometer</span>
                  <strong>{formatMileage(spotlightItem.vehicle.odometer)}</strong>
                </div>
              </div>
              <div className="dashboard-spotlight-copy">
                <p className="dashboard-spotlight-summary">
                  {garageLocation(spotlightItem)} | VIN {maskVin(spotlightItem.vin, isAdminUser(auth) || isPreapproved)}
                </p>
                <p className="dashboard-muted-note">
                  Added {formatDate(spotlightItem.added_at)}
                  {spotlightItem.acquisition_started_at
                    ? ` • Purchase started ${formatDate(spotlightItem.acquisition_started_at)}`
                    : ""}
                </p>
              </div>
              <div className="inventory-actions dashboard-garage-actions">
                <Link className="button secondary" href={`/vinventory/${encodeURIComponent(spotlightItem.public_slug || spotlightItem.vin)}`}>
                  View Details
                </Link>
                {renderGarageReportAction(spotlightItem)}
                <button
                  className="button"
                  onClick={() => startGarageAcquisition(spotlightItem.vin)}
                  disabled={garageActionVin === spotlightItem.vin}
                >
                  {garageActionVin === spotlightItem.vin ? "Starting..." : "Start Purchase"}
                </button>
              </div>
            </>
          ) : (
            <div className="dashboard-empty-state">
              <p style={{ margin: 0 }}>Save a vehicle from VInventory to populate the garage spotlight.</p>
              <Link className="button" href="/vinventory">
                Go to Inventory
              </Link>
            </div>
          )}
        </aside>
      </section>

      {authView !== "onboarding" ? (
        <QuickMatchForm accessToken={accessToken} initialProfile={profileBfv ?? undefined} onCompleted={refreshData} />
      ) : null}

      <section>
        <div className="dashboard-section-head">
          <div>
            <h2>Top Recommendations</h2>
            <p className="dashboard-muted-note">Refreshed from available inventory when My Garage opens.</p>
          </div>
          {recommendations.length ? <span className="badge">{Math.min(recommendations.length, 4)} shown</span> : null}
        </div>
        <RecommendationCards data={recommendations} onSelect={selectVehicle} onFavorite={favoriteVehicle} isAdmin={isAdminUser(auth)} />
      </section>

      <section className="grid two">
        <DannyChat accessToken={accessToken} />

        <div className="card">
          <div className="dashboard-notification-head">
            <h3>Notifications</h3>
            {unreadNotifications.length ? (
              <button className="button ghost" onClick={markNotificationsRead} disabled={markingNotificationsRead}>
                {markingNotificationsRead ? "Marking..." : "Mark All Read"}
              </button>
            ) : null}
          </div>
          {unreadNotifications.length ? unreadNotifications.map((note) => <p key={note.id}>{note.message}</p>) : <p>No notifications yet.</p>}
          {isAdminUser(auth) ? (
            <button className="button" onClick={initiateReturn}>
              Initiate 7-Day Return
            </button>
          ) : null}
        </div>
      </section>

      {crRequestModal ? (
        <div className="dashboard-cr-modal-overlay" onClick={() => setCrRequestModal(null)}>
          <div
            className="card dashboard-cr-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="dashboard-cr-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="dashboard-cr-modal-media">
              <img src={crRequestModal.imageUrl} alt={crRequestModal.title} />
              <div className="dashboard-cr-modal-badge">
                {crRequestModal.alreadyAvailable ? "Report Ready" : "Report In Progress"}
              </div>
            </div>
            <div className="dashboard-cr-modal-copy">
              <p className="section-eyebrow" style={{ marginBottom: 8 }}>
                Inspection Report
              </p>
              <h3 id="dashboard-cr-modal-title">
                {crRequestModal.alreadyAvailable ? "Your report is already available." : "We’re preparing your report now."}
              </h3>
              <p>
                {crRequestModal.alreadyAvailable
                  ? `${crRequestModal.title} already has an inspection report ready in your garage.`
                  : `${crRequestModal.title} has been queued for inspection report preparation. We’ll notify you when it’s complete, and this page will automatically update when the report is ready.`}
              </p>
              <div className="dashboard-cr-modal-actions">
                {crRequestModal.alreadyAvailable ? (
                  <Link
                    className="button ghost-mint"
                    href={`/vinventory/${encodeURIComponent(
                      garageItems.find((item) => item.vin === crRequestModal.vin)?.public_slug || crRequestModal.vin,
                    )}/condition-report`}
                  >
                    Open Report
                  </Link>
                ) : null}
                <button className="button" type="button" onClick={() => setCrRequestModal(null)}>
                  OK
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {surplusReportModal ? (
        <div className="dashboard-cr-modal-overlay" onClick={() => setSurplusReportModal(null)}>
          <div
            className="card dashboard-surplus-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="dashboard-surplus-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="dashboard-surplus-modal-copy">
              <p className="section-eyebrow" style={{ marginBottom: 8 }}>
                Surplus Inventory Inspection
              </p>
              <h3 id="dashboard-surplus-modal-title">{surplusReportModal.title}</h3>
              <p>{surplusReportModal.message}</p>
            </div>
            <div className="dashboard-surplus-gallery">
              {surplusReportModal.images.length ? (
                surplusReportModal.images.map((image, index) => (
                  <img
                    key={`${image}-${index}`}
                    src={image}
                    alt={`${surplusReportModal.title} photo ${index + 1}`}
                    className={cropClassForScreenedImage(image)}
                  />
                ))
              ) : (
                <div className="dashboard-surplus-empty">
                  <p>No screened MarketCheck photos are available yet.</p>
                </div>
              )}
            </div>
            {isAdminUser(auth) && surplusReportModal.hiddenImages.length ? (
              <div className="dashboard-surplus-admin-review">
                <p className="section-eyebrow">Admin Hidden Images</p>
                <div className="dashboard-surplus-gallery dashboard-surplus-hidden-gallery">
                  {surplusReportModal.hiddenImages.map((image, index) => (
                    <label className="dashboard-surplus-hidden-item" key={`${image}-${index}`}>
                      <input
                        type="checkbox"
                        checked={surplusReportModal.selectedHiddenImages.includes(image)}
                        onChange={() => toggleHiddenSurplusImage(image)}
                      />
                      <img
                        src={image}
                        alt={`${surplusReportModal.title} hidden photo ${index + 1}`}
                        className={cropClassForScreenedImage(image)}
                      />
                    </label>
                  ))}
                </div>
                <button
                  className="button ghost"
                  type="button"
                  onClick={publishHiddenSurplusImages}
                  disabled={!surplusReportModal.selectedHiddenImages.length}
                >
                  Publish Selected
                </button>
              </div>
            ) : null}
            <div className="dashboard-surplus-modal-actions">
              <button className="button ghost" type="button" onClick={() => setSurplusReportModal(null)}>
                Cancel
              </button>
              <button className="button" type="button" onClick={orderSurplusConditionReport} disabled={orderingSurplusReport}>
                {orderingSurplusReport ? "Ordering..." : `ORDER REPORT $${surplusReportModal.orderPrice}`}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function garageTitle(item: GarageItem): string {
  const title = `${item.vehicle.year || ""} ${item.vehicle.make || ""} ${item.vehicle.model || ""}`.trim();
  return title || item.vin;
}

function garageLocation(item: GarageItem): string {
  return `${item.vehicle.location_state || "NA"} ${item.vehicle.location_zip || ""}`.trim();
}

function canRequestReportForGarageItem(item: GarageItem): boolean {
  const sourceType = (item.vehicle.source_type || "").toLowerCase();
  return sourceType === "ove" || sourceType === "auction" || isSurplusGarageItem(item);
}

function isSurplusGarageItem(item: GarageItem): boolean {
  const sourceType = (item.vehicle.source_type || "").toLowerCase();
  return sourceType === "marketcheck" || sourceType === "dealer_wholesale" || sourceType === "dealer_partner" || sourceType === "wholesale";
}

function cropClassForScreenedImage(url: string): string | undefined {
  const crop = new URL(url, "https://virtualcarhub.local").hash.match(/vch_crop=([^&]+)/)?.[1];
  return crop ? `dashboard-surplus-crop-${crop}` : undefined;
}

function isReportPending(item: GarageItem, pendingReportVins: Set<string>): boolean {
  return !item.has_inspection_report && (pendingReportVins.has(item.vin) || item.cr_request_status === "pending");
}

function displayModeLabel(mode: DisplayMode): string {
  return mode.replaceAll("_", " ");
}

function inspectionStatusLabel(status: InspectionStatus): string {
  return status.replaceAll("_", " ");
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function sourceLabel(value: string | null | undefined): string {
  return toPublicSourceLabel(value);
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "N/A";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  }).format(new Date(value));
}

function formatMileage(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `${value.toLocaleString()} mi`;
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `$${value.toLocaleString()}`;
}
