/**
 * ReviewScreen — displays analysis results (risk flags) for a completed job.
 * Navigation target from DiffScreen when analysis is available.
 */
import React from 'react';
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Feather } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useAuth } from '@/context/auth';
import { getAnalysisResults, RiskFlagResponse } from '@/lib/api';

const SEVERITY_CONFIG: Record<string, { label: string; colorKey: string; icon: string }> = {
  critical: { label: 'Kritis', colorKey: 'rose', icon: 'alert-octagon' },
  high: { label: 'Tinggi', colorKey: 'amber', icon: 'alert-triangle' },
  medium: { label: 'Sedang', colorKey: 'amber', icon: 'alert-circle' },
  info: { label: 'Info', colorKey: 'violet', icon: 'info' },
};

function RiskFlagCard({
  flag,
  colors,
}: {
  flag: RiskFlagResponse;
  colors: ReturnType<typeof useColors>;
}) {
  const sev = SEVERITY_CONFIG[flag.severity] ?? SEVERITY_CONFIG.info;
  const bgKey = (sev.colorKey + 'Bg') as keyof typeof colors;
  const borderKey = (sev.colorKey + 'Border') as keyof typeof colors;
  const fgKey = (sev.colorKey + 'Foreground') as keyof typeof colors;
  const colorKey = sev.colorKey as keyof typeof colors;

  const bg = colors[bgKey] as string;
  const border = colors[borderKey] as string;
  const fg = colors[fgKey] as string;
  const color = colors[colorKey] as string;

  return (
    <View style={[styles.flagCard, { borderLeftColor: color, borderLeftWidth: 3, backgroundColor: colors.card, borderColor: colors.border }]}>
      <View style={styles.flagHeader}>
        <Feather name={sev.icon as any} size={16} color={color} />
        <View style={[styles.sevBadge, { backgroundColor: bg, borderColor: border }]}>
          <Text style={[styles.sevText, { color: fg }]}>{sev.label}</Text>
        </View>
        <Text style={[styles.domain, { color: colors.mutedForeground }]}>{flag.domain}</Text>
      </View>

      <Text style={[styles.flagSummary, { color: colors.foreground }]}>{flag.summary}</Text>

      {flag.rationale && (
        <View style={[styles.rationaleBox, { backgroundColor: colors.muted, borderColor: colors.border }]}>
          <Text style={[styles.rationaleLabel, { color: colors.mutedForeground }]}>Mengapa ini penting</Text>
          <Text style={[styles.rationaleText, { color: colors.foreground }]}>{flag.rationale}</Text>
        </View>
      )}

      {flag.negotiation_ask && (
        <View style={[styles.negotiationBox, { backgroundColor: colors.violetBg, borderColor: colors.violetBorder }]}>
          <View style={styles.negotiationHeader}>
            <Feather name="message-square" size={13} color={colors.violet} />
            <Text style={[styles.negotiationLabel, { color: colors.violetForeground }]}>Saran Negosiasi</Text>
          </View>
          <Text style={[styles.negotiationText, { color: colors.foreground }]}>{flag.negotiation_ask}</Text>
        </View>
      )}
    </View>
  );
}

export default function ReviewScreen() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { jobId } = useLocalSearchParams<{ jobId: string }>();

  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['analysis-results', jobId, user?.user_id],
    queryFn: () => getAnalysisResults(jobId),
    retry: 1,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d || d.state === 'done' || d.state === 'failed') return false;
      return 3000;
    },
  });

  const topPad = Platform.OS === 'web' ? 67 : insets.top;
  const bottomPad = Platform.OS === 'web' ? 34 : insets.bottom;

  const flagCounts = data?.flag_counts;
  const flags = data?.risk_flags ?? [];
  const isRunning = data && !['done', 'failed'].includes(data.state);

  return (
    <View style={[styles.root, { paddingBottom: bottomPad, backgroundColor: colors.background }]}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: topPad + 12, borderBottomColor: colors.border, backgroundColor: colors.card }]}>
        <Pressable
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.6 }]}
          onPress={() => router.back()}
          hitSlop={8}
        >
          <Feather name="chevron-left" size={22} color={colors.foreground} />
        </Pressable>
        <View style={styles.headerCenter}>
          <View style={[styles.brandMini, { backgroundColor: colors.primary }]}>
            <Feather name="shield" size={13} color={colors.primaryForeground} />
          </View>
          <Text style={[styles.headerTitle, { color: colors.foreground }]} numberOfLines={1}>
            Hasil Analisis
          </Text>
        </View>
        <View style={{ width: 36 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={32} color={colors.amber} />
          <Text style={[styles.errorTitle, { color: colors.foreground }]}>Gagal memuat analisis</Text>
          <Text style={[styles.errorSub, { color: colors.mutedForeground }]}>{(error as Error).message}</Text>
          <Pressable
            style={({ pressed }) => [styles.retryBtn, { backgroundColor: colors.secondary }, pressed && { opacity: 0.7 }]}
            onPress={() => refetch()}
          >
            <Text style={[styles.retryText, { color: colors.foreground }]}>Coba lagi</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={flags}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
          ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
          ListHeaderComponent={
            data ? (
              <View style={{ gap: 12, marginBottom: 14 }}>
                {/* Running state */}
                {isRunning && (
                  <View style={[styles.runningBanner, { backgroundColor: colors.amberBg, borderColor: colors.amberBorder }]}>
                    <ActivityIndicator size="small" color={colors.amber} />
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.runningTitle, { color: colors.amberForeground }]}>
                        Analisis sedang berjalan
                      </Text>
                      <Text style={[styles.runningSub, { color: colors.amberForeground }]}>
                        {data.stage ?? 'Memproses dokumen…'}
                      </Text>
                    </View>
                  </View>
                )}

                {/* Failed state */}
                {data.state === 'failed' && (
                  <View style={[styles.runningBanner, { backgroundColor: colors.redBg, borderColor: colors.redBorder }]}>
                    <Feather name="x-circle" size={18} color={colors.red} />
                    <Text style={[styles.runningTitle, { color: colors.destructive }]}>
                      Analisis gagal: {data.error_message ?? 'Kesalahan tidak diketahui.'}
                    </Text>
                  </View>
                )}

                {/* Flag counts summary */}
                {flagCounts && (
                  <View style={[styles.countRow, { backgroundColor: colors.card, borderColor: colors.border }]}>
                    {(['critical', 'high', 'medium', 'info'] as const).map((sev) => {
                      const count = flagCounts[sev] ?? 0;
                      if (!count) return null;
                      const cfg = SEVERITY_CONFIG[sev];
                      const color = colors[cfg.colorKey as keyof typeof colors] as string;
                      return (
                        <View key={sev} style={styles.countItem}>
                          <Text style={[styles.countNumber, { color }]}>{count}</Text>
                          <Text style={[styles.countLabel, { color: colors.mutedForeground }]}>
                            {cfg.label}
                          </Text>
                        </View>
                      );
                    })}
                  </View>
                )}

                {flags.length > 0 && (
                  <Text style={[styles.sectionHeader, { color: colors.mutedForeground }]}>
                    Temuan Risiko ({flags.length})
                  </Text>
                )}
              </View>
            ) : null
          }
          ListEmptyComponent={
            data?.state === 'done' ? (
              <View style={styles.emptyState}>
                <Feather name="check-circle" size={40} color={colors.green} />
                <Text style={[styles.emptyTitle, { color: colors.foreground }]}>Tidak ada risiko ditemukan</Text>
                <Text style={[styles.emptySub, { color: colors.mutedForeground }]}>
                  Analisis selesai — tidak ada flag risiko yang teridentifikasi.
                </Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => <RiskFlagCard flag={item} colors={colors} />}
        />
      )}

      {/* Disclaimer footer */}
      <View style={[styles.disclaimer, { borderTopColor: colors.border, backgroundColor: colors.card }]}>
        <Feather name="info" size={11} color={colors.mutedForeground} />
        <Text style={[styles.disclaimerText, { color: colors.mutedForeground }]}>
          Hasil AI — selalu verifikasi dengan advokat sebelum menandatangani.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    gap: 10,
  },
  backBtn: { padding: 4 },
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
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 15,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
    flex: 1,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 12,
  },
  errorTitle: {
    fontSize: 17,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
    textAlign: 'center',
  },
  errorSub: {
    fontSize: 14,
    fontFamily: 'Inter_400Regular',
    textAlign: 'center',
  },
  retryBtn: {
    marginTop: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  retryText: {
    fontSize: 14,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
  },
  listContent: { padding: 16, paddingBottom: 24 },
  runningBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    borderWidth: 1,
    borderRadius: 12,
    padding: 14,
  },
  runningTitle: {
    fontSize: 14,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
  },
  runningSub: {
    fontSize: 12,
    fontFamily: 'Inter_400Regular',
    marginTop: 2,
  },
  countRow: {
    flexDirection: 'row',
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    justifyContent: 'space-around',
  },
  countItem: {
    alignItems: 'center',
    gap: 2,
  },
  countNumber: {
    fontSize: 22,
    fontWeight: '700' as const,
    fontFamily: 'Inter_700Bold',
  },
  countLabel: {
    fontSize: 11,
    fontFamily: 'Inter_500Medium',
    fontWeight: '500' as const,
  },
  sectionHeader: {
    fontSize: 11,
    fontWeight: '700' as const,
    fontFamily: 'Inter_700Bold',
    textTransform: 'uppercase' as const,
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
    fontFamily: 'Inter_600SemiBold',
  },
  emptySub: {
    fontSize: 14,
    fontFamily: 'Inter_400Regular',
    textAlign: 'center',
    lineHeight: 20,
    maxWidth: 260,
  },
  flagCard: {
    borderRadius: 12,
    borderWidth: 1,
    overflow: 'hidden' as const,
    padding: 14,
    gap: 10,
  },
  flagHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap' as const,
  },
  sevBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
  },
  sevText: {
    fontSize: 11,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
  },
  domain: {
    fontSize: 12,
    fontFamily: 'Inter_400Regular',
    flex: 1,
  },
  flagSummary: {
    fontSize: 14,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 20,
  },
  rationaleBox: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    gap: 4,
  },
  rationaleLabel: {
    fontSize: 11,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  rationaleText: {
    fontSize: 13,
    fontFamily: 'Inter_400Regular',
    lineHeight: 18,
  },
  negotiationBox: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    gap: 6,
  },
  negotiationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  negotiationLabel: {
    fontSize: 11,
    fontWeight: '600' as const,
    fontFamily: 'Inter_600SemiBold',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  negotiationText: {
    fontSize: 13,
    fontFamily: 'Inter_400Regular',
    lineHeight: 18,
  },
  disclaimer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderTopWidth: 1,
  },
  disclaimerText: {
    fontSize: 11,
    fontFamily: 'Inter_400Regular',
    flex: 1,
    lineHeight: 15,
  },
});
