/**
 * DiffScreen — clause-level diff view with materiality classification.
 * Mirrors DiffPage.tsx from the web app, adapted for mobile.
 * Supports: expired-banner dismiss, start analysis, navigate to review.
 */
import React, { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Feather } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useColors } from '@/hooks/useColors';
import { useAuth } from '@/context/auth';
import { getVersionDiff, triggerAnalysis, VersionDiffRow, VersionDiffResponse } from '@/lib/api';

const ANALYSIS_TTL_MS = 10 * 60 * 1000;

function sessionKey(versionId: string) {
  return `landy_analysis_pending_${versionId}`;
}

// ── Diff card ─────────────────────────────────────────────────────────────────

const CHANGE_KIND_CONFIG = {
  added: { label: 'Ditambahkan', colorKey: 'green' as const },
  removed: { label: 'Dihapus', colorKey: 'red' as const },
  modified: { label: 'Diubah', colorKey: 'amber' as const },
};

// Total mapping — an unrecognised change kind renders its raw label loudly
// instead of being silently relabelled 'Diubah' (LC-41 pattern).
function changeKindConfig(kind: string): { label: string; colorKey: 'green' | 'red' | 'amber' } {
  const cfg = CHANGE_KIND_CONFIG[kind as keyof typeof CHANGE_KIND_CONFIG];
  if (cfg) return cfg;
  return { label: kind, colorKey: 'amber' };
}

function DiffCard({
  row,
  jobId,
  colors,
  onNavigateReview,
  onStartAnalysis,
  triggeringAnalysis,
}: {
  row: VersionDiffRow;
  jobId: string | null;
  colors: ReturnType<typeof useColors>;
  onNavigateReview: (clauseRef: string | null) => void;
  onStartAnalysis: () => void;
  triggeringAnalysis: boolean;
}) {
  const styles = makeDiffCardStyles(colors);
  const isMaterial = row.materiality === 'material';
  // A failed classification is co-equal in prominence to material — the
  // change must never render as quiet 'not material' (LC-41).
  const isUnclassified = row.classification_status === 'failed' || row.materiality == null;
  const kindCfg = changeKindConfig(row.change_kind);

  const kindBg = colors[kindCfg.colorKey + 'Bg' as keyof typeof colors] as string;
  const kindBorder = colors[kindCfg.colorKey + 'Border' as keyof typeof colors] as string;
  const kindFg = colors[kindCfg.colorKey as keyof typeof colors] as string;

  return (
    <View
      style={[
        styles.card,
        isMaterial
          ? { borderLeftColor: colors.rose, borderLeftWidth: 3 }
          : isUnclassified
            ? { borderLeftColor: colors.amber, borderLeftWidth: 3 }
            : { borderLeftColor: colors.border, borderLeftWidth: 3 },
      ]}
    >
      {/* Card header */}
      <View style={styles.cardHeader}>
        <Feather
          name={row.change_kind === 'added' ? 'plus-circle' : row.change_kind === 'removed' ? 'minus-circle' : 'refresh-cw'}
          size={14}
          color={kindFg}
        />
        <Text style={styles.clauseRef} numberOfLines={1}>
          {row.clause_ref ?? 'Klausul tanpa referensi'}
        </Text>
      </View>

      {/* Badges */}
      <View style={styles.badgeRow}>
        <View style={[styles.badge, { backgroundColor: kindBg, borderColor: kindBorder }]}>
          <Text style={[styles.badgeText, { color: kindFg }]}>{kindCfg.label}</Text>
        </View>
        <View
          style={[
            styles.badge,
            isMaterial
              ? { backgroundColor: colors.roseBg, borderColor: colors.roseBorder }
              : isUnclassified
                ? { backgroundColor: colors.amberBg, borderColor: colors.amberBorder }
                : { backgroundColor: colors.muted, borderColor: colors.border },
          ]}
        >
          <Text
            style={[
              styles.badgeText,
              {
                color: isMaterial
                  ? colors.roseForeground
                  : isUnclassified
                    ? colors.amberForeground
                    : colors.mutedForeground,
              },
            ]}
          >
            {isMaterial
              ? 'Material'
              : isUnclassified
                ? 'Belum Terklasifikasi'
                : 'Tidak Material'}
          </Text>
        </View>
      </View>

      {/* Materiality reason — or the honest unclassified state */}
      {isUnclassified ? (
        <Text style={[styles.reason, { color: colors.amberForeground }]}>
          Perubahan ini belum bisa diklasifikasikan secara otomatis — tinjau
          klausul ini secara mandiri.
        </Text>
      ) : (
        row.materiality_reason && (
          <Text style={styles.reason}>{row.materiality_reason}</Text>
        )
      )}

      {/* Text content */}
      {row.before_text && (
        <View style={[styles.textBlock, { backgroundColor: colors.redBg, borderColor: colors.redBorder }]}>
          <Text style={[styles.textBlockLabel, { color: colors.red }]}>
            {row.change_kind === 'removed' ? 'Klausul dihapus' : 'Teks sebelumnya'}
          </Text>
          <Text style={[styles.textBlockBody, { color: colors.foreground }]}>{row.before_text}</Text>
        </View>
      )}

      {row.change_kind === 'modified' && row.before_text && row.after_text && (
        <View style={styles.dividerRow}>
          <View style={[styles.dividerLine, { backgroundColor: colors.border }]} />
          <Text style={styles.dividerLabel}>diubah menjadi</Text>
          <View style={[styles.dividerLine, { backgroundColor: colors.border }]} />
        </View>
      )}

      {row.after_text && (
        <View style={[styles.textBlock, { backgroundColor: colors.greenBg, borderColor: colors.greenBorder }]}>
          <Text style={[styles.textBlockLabel, { color: colors.green }]}>
            {row.change_kind === 'added' ? 'Klausul baru' : 'Teks baru'}
          </Text>
          <Text style={[styles.textBlockBody, { color: colors.foreground }]}>{row.after_text}</Text>
        </View>
      )}

      {/* Material CTA */}
      {isMaterial && (
        <View style={styles.ctaRow}>
          {jobId ? (
            <Pressable
              style={({ pressed }) => [styles.ctaLink, pressed && { opacity: 0.6 }]}
              onPress={() => onNavigateReview(row.clause_ref)}
            >
              <Feather name="arrow-right" size={13} color={colors.primary} />
              <Text style={[styles.ctaLinkText, { color: colors.primary }]}>
                Lihat Saran Negosiasi
              </Text>
            </Pressable>
          ) : (
            <Pressable
              style={({ pressed }) => [styles.ctaLink, pressed && { opacity: 0.6 }, triggeringAnalysis && { opacity: 0.5 }]}
              onPress={onStartAnalysis}
              disabled={triggeringAnalysis}
            >
              {triggeringAnalysis ? (
                <ActivityIndicator size="small" color={colors.mutedForeground} />
              ) : (
                <Feather name="zap" size={13} color={colors.mutedForeground} />
              )}
              <Text style={[styles.ctaLinkText, { color: colors.mutedForeground }]}>
                Mulai Analisis
              </Text>
            </Pressable>
          )}
        </View>
      )}
    </View>
  );
}

function makeDiffCardStyles(colors: ReturnType<typeof useColors>) {
  return StyleSheet.create({
    card: {
      backgroundColor: colors.card,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: colors.border,
      overflow: 'hidden' as const,
      gap: 10,
      padding: 14,
    },
    cardHeader: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: 8,
    },
    clauseRef: {
      fontSize: 14,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
      flex: 1,
    },
    badgeRow: {
      flexDirection: 'row' as const,
      gap: 6,
      flexWrap: 'wrap' as const,
    },
    badge: {
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 5,
      borderWidth: 1,
    },
    badgeText: {
      fontSize: 11,
      fontWeight: '500' as const,
      fontFamily: 'Inter_500Medium',
    },
    reason: {
      fontSize: 12,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      fontStyle: 'italic' as const,
      lineHeight: 17,
    },
    textBlock: {
      borderWidth: 1,
      borderRadius: 8,
      padding: 12,
      gap: 6,
    },
    textBlockLabel: {
      fontSize: 11,
      fontWeight: '700' as const,
      fontFamily: 'Inter_700Bold',
      textTransform: 'uppercase' as const,
      letterSpacing: 0.6,
    },
    textBlockBody: {
      fontSize: 13,
      lineHeight: 19,
      fontFamily: 'Inter_400Regular',
    },
    dividerRow: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: 8,
    },
    dividerLine: {
      flex: 1,
      height: 1,
    },
    dividerLabel: {
      fontSize: 11,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
    },
    ctaRow: {
      borderTopWidth: 1,
      borderTopColor: colors.border,
      paddingTop: 10,
    },
    ctaLink: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: 5,
    },
    ctaLinkText: {
      fontSize: 13,
      fontWeight: '500' as const,
      fontFamily: 'Inter_500Medium',
    },
  });
}

// ── Main DiffScreen ───────────────────────────────────────────────────────────

export default function DiffScreen() {
  const colors = useColors();
  const styles = makeStyles(colors);
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { docId, versionId } = useLocalSearchParams<{ docId: string; versionId: string }>();

  // Expired-banner state (persisted in AsyncStorage across reloads)
  const [showExpiredBanner, setShowExpiredBanner] = useState(false);
  const [triggeringAnalysis, setTriggeringAnalysis] = useState(false);
  const analysisInFlight = useRef(false);
  const [showMaterialOnly, setShowMaterialOnly] = useState(false);

  // On first load, check if a pending analysis session exists and has expired
  const [initDone, setInitDone] = useState(false);
  React.useEffect(() => {
    async function checkExpired() {
      const key = sessionKey(versionId);
      const raw = await AsyncStorage.getItem(key);
      if (raw) {
        const expiry = Number(raw);
        if (isNaN(expiry) || Date.now() > expiry) {
          await AsyncStorage.removeItem(key);
          setShowExpiredBanner(true);
        } else {
          setTriggeringAnalysis(true);
        }
      }
      setInitDone(true);
    }
    checkExpired();
  }, [versionId]);

  const { user } = useAuth();
  const { data: diff, isLoading, error, refetch } = useQuery({
    queryKey: ['diff', docId, versionId, user?.user_id],
    queryFn: () => getVersionDiff(docId, versionId),
    enabled: initDone && !!user?.user_id,
    retry: 1,
  });

  // Clear the pending flag when the analysis job has completed.
  React.useEffect(() => {
    if (diff?.job_id) {
      AsyncStorage.removeItem(sessionKey(versionId));
      setTriggeringAnalysis(false);
      analysisInFlight.current = false;
    }
  }, [diff?.job_id, versionId]);

  const handleNavigateReview = useCallback(
    (clauseRef: string | null) => {
      if (!diff?.job_id) return;
      router.push(`/review/${diff.job_id}`);
    },
    [diff, router],
  );

  const handleTriggerAnalysis = useCallback(async () => {
    if (!diff || analysisInFlight.current || triggeringAnalysis) return;
    analysisInFlight.current = true;
    const key = sessionKey(versionId);
    await AsyncStorage.setItem(key, String(Date.now() + ANALYSIS_TTL_MS));
    setTriggeringAnalysis(true);
    setShowExpiredBanner(false);
    try {
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      const job = await triggerAnalysis(diff.to_version_id);
      await AsyncStorage.removeItem(key);
      router.push(`/review/${job.job_id}`);
    } catch (err: unknown) {
      analysisInFlight.current = false;
      await AsyncStorage.removeItem(key);
      setTriggeringAnalysis(false);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    }
  }, [diff, triggeringAnalysis, versionId, router]);

  const filteredDiffs: VersionDiffRow[] = diff
    ? showMaterialOnly
      ? diff.diffs.filter((d) => d.materiality === 'material')
      : diff.diffs
    : [];

  const topPad = Platform.OS === 'web' ? 67 : insets.top;
  const bottomPad = Platform.OS === 'web' ? 34 : insets.bottom;

  return (
    <View style={[styles.root, { paddingBottom: bottomPad }]}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: topPad + 12 }]}>
        <Pressable
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.6 }]}
          onPress={() => router.back()}
          hitSlop={8}
        >
          <Feather name="chevron-left" size={22} color={colors.foreground} />
        </Pressable>
        <View style={styles.headerCenter}>
          <View style={styles.brandMini}>
            <Feather name="shield" size={13} color={colors.primaryForeground} />
          </View>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {diff
              ? `v${diff.from_version_no} → v${diff.to_version_no}`
              : 'Perbandingan Versi'}
          </Text>
        </View>
        {diff?.job_id ? (
          <Pressable
            style={({ pressed }) => [styles.headerCta, pressed && { opacity: 0.8 }]}
            onPress={() => handleNavigateReview(null)}
          >
            <Feather name="eye" size={13} color={colors.primaryForeground} />
          </Pressable>
        ) : diff && diff.material_count > 0 ? (
          <Pressable
            style={({ pressed }) => [styles.headerCta, { backgroundColor: colors.secondary }, pressed && { opacity: 0.8 }]}
            onPress={handleTriggerAnalysis}
            disabled={triggeringAnalysis}
          >
            {triggeringAnalysis ? (
              <ActivityIndicator size="small" color={colors.foreground} />
            ) : (
              <Feather name="zap" size={13} color={colors.foreground} />
            )}
          </Pressable>
        ) : (
          <View style={{ width: 36 }} />
        )}
      </View>

      {/* Body */}
      {isLoading || !initDone ? (
        <View style={styles.loadingCenter}>
          <ActivityIndicator color={colors.primary} size="large" />
        </View>
      ) : error ? (
        <View style={styles.loadingCenter}>
          <Feather name="alert-triangle" size={32} color={colors.amber} />
          <Text style={styles.errorTitle}>Perbandingan tidak tersedia</Text>
          <Text style={styles.errorSub}>{(error as Error).message}</Text>
          <Pressable style={({ pressed }) => [styles.retryBtn, pressed && { opacity: 0.7 }]} onPress={() => refetch()}>
            <Text style={styles.retryText}>Coba lagi</Text>
          </Pressable>
        </View>
      ) : diff ? (
        <FlatList
          data={filteredDiffs}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          ListHeaderComponent={
            <DiffListHeader
              diff={diff}
              colors={colors}
              showMaterialOnly={showMaterialOnly}
              onToggleMaterial={() => setShowMaterialOnly((v) => !v)}
              showExpiredBanner={showExpiredBanner}
              triggeringAnalysis={triggeringAnalysis}
              onDismissBanner={() => setShowExpiredBanner(false)}
              onTriggerAnalysis={handleTriggerAnalysis}
            />
          }
          ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
          renderItem={({ item }) => (
            <DiffCard
              row={item}
              jobId={diff.job_id}
              colors={colors}
              onNavigateReview={handleNavigateReview}
              onStartAnalysis={handleTriggerAnalysis}
              triggeringAnalysis={triggeringAnalysis}
            />
          )}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Feather name="check-circle" size={36} color={colors.green} />
              <Text style={styles.emptyTitle}>
                {showMaterialOnly ? 'Tidak ada perubahan material' : 'Tidak ada perubahan'}
              </Text>
            </View>
          }
        />
      ) : null}
    </View>
  );
}

// ── DiffListHeader ────────────────────────────────────────────────────────────

function DiffListHeader({
  diff,
  colors,
  showMaterialOnly,
  onToggleMaterial,
  showExpiredBanner,
  triggeringAnalysis,
  onDismissBanner,
  onTriggerAnalysis,
}: {
  diff: VersionDiffResponse;
  colors: ReturnType<typeof useColors>;
  showMaterialOnly: boolean;
  onToggleMaterial: () => void;
  showExpiredBanner: boolean;
  triggeringAnalysis: boolean;
  onDismissBanner: () => void;
  onTriggerAnalysis: () => void;
}) {
  const styles = makeStyles(colors);
  return (
    <View style={{ gap: 12, marginBottom: 12 }}>
      {/* Summary card */}
      <View style={styles.summaryCard}>
        <View style={styles.summaryTop}>
          <View>
            <Text style={styles.summaryHeading}>
              v{diff.from_version_no} → v{diff.to_version_no}
            </Text>
            <Text style={styles.summarySub}>{diff.total_changes} klausul berubah</Text>
          </View>
          <View style={styles.summaryBadges}>
            {diff.material_count > 0 && (
              <View style={[styles.summaryBadge, { backgroundColor: colors.roseBg, borderColor: colors.roseBorder }]}>
                <Feather name="alert-triangle" size={11} color={colors.rose} />
                <Text style={[styles.summaryBadgeText, { color: colors.roseForeground }]}>
                  {diff.material_count} material
                </Text>
              </View>
            )}
            {diff.immaterial_count > 0 && (
              <View style={[styles.summaryBadge, { backgroundColor: colors.muted, borderColor: colors.border }]}>
                <Feather name="info" size={11} color={colors.mutedForeground} />
                <Text style={[styles.summaryBadgeText, { color: colors.mutedForeground }]}>
                  {diff.immaterial_count} tdk material
                </Text>
              </View>
            )}
          </View>
        </View>

        {diff.material_count > 0 && diff.immaterial_count > 0 && (
          <Pressable
            style={({ pressed }) => [styles.toggleBtn, pressed && { opacity: 0.7 }]}
            onPress={onToggleMaterial}
          >
            <Text style={styles.toggleBtnText}>
              {showMaterialOnly ? 'Tampilkan semua' : 'Material saja'}
            </Text>
          </Pressable>
        )}

        <View style={styles.infoRow}>
          <Feather name="info" size={12} color={colors.mutedForeground} />
          <Text style={styles.infoText}>
            Perubahan <Text style={{ fontFamily: 'Inter_600SemiBold' }}>material</Text> menggeser posisi hukum Anda.{' '}
            <Text style={{ fontFamily: 'Inter_600SemiBold' }}>Tidak material</Text> bersifat redaksional.
          </Text>
        </View>
      </View>

      {/* Expired-analysis banner */}
      {!diff.job_id && diff.material_count > 0 && showExpiredBanner && (
        <View style={[styles.banner, { backgroundColor: colors.amberBg, borderColor: colors.amberBorder }]}>
          <Feather name="alert-triangle" size={18} color={colors.amber} />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[styles.bannerTitle, { color: colors.amberForeground }]}>
              Analisis sebelumnya tidak selesai
            </Text>
            <Text style={[styles.bannerSub, { color: colors.amberForeground }]}>
              Sesi analisis habis waktu. Mulai kembali untuk mendapatkan saran negosiasi.
            </Text>
          </View>
          <View style={{ gap: 8, alignItems: 'flex-end' as const }}>
            <Pressable
              style={({ pressed }) => [styles.bannerBtn, { backgroundColor: colors.amber }, pressed && { opacity: 0.8 }]}
              onPress={onTriggerAnalysis}
              disabled={triggeringAnalysis}
            >
              {triggeringAnalysis ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Feather name="refresh-cw" size={13} color="#fff" />
              )}
            </Pressable>
            <Pressable onPress={onDismissBanner} hitSlop={8}>
              <Feather name="x" size={16} color={colors.amberForeground} />
            </Pressable>
          </View>
        </View>
      )}

      {/* No-analysis prompt */}
      {!diff.job_id && diff.material_count > 0 && !showExpiredBanner && (
        <View style={[styles.banner, { backgroundColor: colors.violetBg, borderColor: colors.violetBorder }]}>
          <Feather name="zap" size={18} color={colors.violet} />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[styles.bannerTitle, { color: colors.violetForeground }]}>
              Analisis belum tersedia
            </Text>
            <Text style={[styles.bannerSub, { color: colors.violetForeground }]}>
              {diff.material_count} perubahan material perlu ditinjau. Mulai analisis untuk saran negosiasi.
            </Text>
          </View>
          <Pressable
            style={({ pressed }) => [styles.bannerBtn, { backgroundColor: colors.violet }, pressed && { opacity: 0.8 }]}
            onPress={onTriggerAnalysis}
            disabled={triggeringAnalysis}
          >
            {triggeringAnalysis ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Feather name="zap" size={13} color="#fff" />
            )}
          </Pressable>
        </View>
      )}

      {/* Material section header */}
      {!showMaterialOnly && diff.material_count > 0 && (
        <Text style={styles.sectionHeader}>
          Perubahan Material ({diff.material_count})
        </Text>
      )}
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

function makeStyles(colors: ReturnType<typeof useColors>) {
  return StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: colors.background,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 16,
      paddingBottom: 12,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
      backgroundColor: colors.card,
      gap: 10,
    },
    backBtn: {
      padding: 4,
    },
    headerCenter: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
    },
    brandMini: {
      width: 22,
      height: 22,
      borderRadius: 6,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    headerTitle: {
      fontSize: 15,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
      flex: 1,
    },
    headerCta: {
      width: 36,
      height: 36,
      borderRadius: 10,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    loadingCenter: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
      gap: 12,
    },
    errorTitle: {
      fontSize: 17,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
      textAlign: 'center',
    },
    errorSub: {
      fontSize: 14,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      textAlign: 'center',
    },
    retryBtn: {
      marginTop: 8,
      paddingHorizontal: 20,
      paddingVertical: 10,
      backgroundColor: colors.secondary,
      borderRadius: 8,
    },
    retryText: {
      fontSize: 14,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
    },
    listContent: {
      padding: 16,
      paddingBottom: 32,
    },
    summaryCard: {
      backgroundColor: colors.card,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: colors.border,
      padding: 16,
      gap: 12,
    },
    summaryTop: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      gap: 8,
    },
    summaryHeading: {
      fontSize: 16,
      fontWeight: '700' as const,
      color: colors.foreground,
      fontFamily: 'Inter_700Bold',
    },
    summarySub: {
      fontSize: 12,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      marginTop: 2,
    },
    summaryBadges: {
      gap: 5,
      alignItems: 'flex-end',
    },
    summaryBadge: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      paddingHorizontal: 8,
      paddingVertical: 4,
      borderRadius: 12,
      borderWidth: 1,
    },
    summaryBadgeText: {
      fontSize: 11,
      fontWeight: '500' as const,
      fontFamily: 'Inter_500Medium',
    },
    toggleBtn: {
      alignSelf: 'flex-start',
      paddingHorizontal: 12,
      paddingVertical: 6,
      backgroundColor: colors.secondary,
      borderRadius: 6,
    },
    toggleBtnText: {
      fontSize: 12,
      fontWeight: '500' as const,
      color: colors.foreground,
      fontFamily: 'Inter_500Medium',
    },
    infoRow: {
      flexDirection: 'row',
      gap: 6,
      borderTopWidth: 1,
      borderTopColor: colors.border,
      paddingTop: 10,
    },
    infoText: {
      fontSize: 12,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      flex: 1,
      lineHeight: 17,
    },
    banner: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 12,
      borderWidth: 1,
      borderRadius: 12,
      padding: 14,
    },
    bannerTitle: {
      fontSize: 14,
      fontWeight: '600' as const,
      fontFamily: 'Inter_600SemiBold',
    },
    bannerSub: {
      fontSize: 12,
      fontFamily: 'Inter_400Regular',
      lineHeight: 17,
    },
    bannerBtn: {
      width: 34,
      height: 34,
      borderRadius: 8,
      alignItems: 'center',
      justifyContent: 'center',
    },
    sectionHeader: {
      fontSize: 11,
      fontWeight: '700' as const,
      fontFamily: 'Inter_700Bold',
      color: colors.roseForeground,
      textTransform: 'uppercase',
      letterSpacing: 0.8,
    },
    emptyState: {
      alignItems: 'center',
      paddingVertical: 48,
      gap: 10,
    },
    emptyTitle: {
      fontSize: 16,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
    },
  });
}
