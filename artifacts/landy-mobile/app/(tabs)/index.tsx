import React, { useCallback, useEffect } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
  Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Feather } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useColors } from '@/hooks/useColors';
import { useAuth } from '@/context/auth';
import { listDocuments, logout, DocumentListItem } from '@/lib/api';

export default function HomeScreen() {
  const colors = useColors();
  const styles = makeStyles(colors);
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { token, user, clearSession, isLoading: authLoading } = useAuth();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !token) {
      router.replace('/login');
    }
  }, [authLoading, token, router]);

  const {
    data: documents,
    isLoading,
    isRefetching,
    refetch,
    error,
  } = useQuery({
    queryKey: ['documents', user?.user_id],
    queryFn: listDocuments,
    enabled: !!token && !!user?.user_id,
    retry: 1,
  });

  const handleLogout = useCallback(async () => {
    try {
      await logout();
    } finally {
      await clearSession();
      router.replace('/login');
    }
  }, [clearSession, router]);

  const handleOpenDiff = useCallback(
    async (doc: DocumentListItem) => {
      if (!doc.latest_version || doc.version_count < 2) return;
      await Haptics.selectionAsync();
      router.push(`/diff/${doc.id}/${doc.latest_version.id}`);
    },
    [router],
  );

  const handleOpenReview = useCallback(
    async (jobId: string) => {
      await Haptics.selectionAsync();
      router.push(`/review/${jobId}`);
    },
    [router],
  );

  if (authLoading) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }

  if (!token) return null;

  const topPad = Platform.OS === 'web' ? 67 : insets.top;
  const bottomPad = Platform.OS === 'web' ? 34 : insets.bottom;

  return (
    <View style={[styles.root, { paddingBottom: bottomPad }]}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: topPad + 16 }]}>
        <View style={styles.brandRow}>
          <View style={styles.brandIcon}>
            <Feather name="shield" size={16} color={colors.primaryForeground} />
          </View>
          <Text style={styles.brandName}>LANDY</Text>
        </View>
        <View style={styles.headerRight}>
          {user && (
            <Text style={styles.userEmail} numberOfLines={1}>
              {user.display_name ?? user.email}
            </Text>
          )}
          <Pressable
            style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.6 }]}
            onPress={handleLogout}
            hitSlop={8}
          >
            <Feather name="log-out" size={18} color={colors.mutedForeground} />
          </Pressable>
        </View>
      </View>

      {/* Disclaimer */}
      <View style={styles.disclaimerRow}>
        <Feather name="info" size={12} color={colors.mutedForeground} />
        <Text style={styles.disclaimerText}>
          Klasifikasi AI — verifikasi dengan advokat sebelum menandatangani.
        </Text>
      </View>

      {/* Body */}
      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} size="large" />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Feather name="alert-triangle" size={32} color={colors.amber} />
          <Text style={styles.errorTitle}>Gagal memuat dokumen</Text>
          <Text style={styles.errorSub}>{(error as Error).message}</Text>
          <Pressable style={({ pressed }) => [styles.retryBtn, pressed && { opacity: 0.7 }]} onPress={() => refetch()}>
            <Text style={styles.retryText}>Coba lagi</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={documents ?? []}
          keyExtractor={(item) => item.id}
          contentContainerStyle={[styles.listContent, !(documents?.length) && styles.emptyContent]}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor={colors.primary}
            />
          }
          ListHeaderComponent={
            <Text style={styles.sectionTitle}>
              Dokumen ({documents?.length ?? 0})
            </Text>
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Feather name="file-text" size={40} color={colors.border} />
              <Text style={styles.emptyTitle}>Belum ada dokumen</Text>
              <Text style={styles.emptySub}>
                Upload kontrak dari aplikasi web LANDY untuk mulai meninjau perubahan.
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <DocumentCard
              doc={item}
              colors={colors}
              onOpenDiff={handleOpenDiff}
              onOpenReview={handleOpenReview}
            />
          )}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          scrollEnabled={!!(documents?.length)}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

// ── DocumentCard ─────────────────────────────────────────────────────────────

function DocumentCard({
  doc,
  colors,
  onOpenDiff,
  onOpenReview,
}: {
  doc: DocumentListItem;
  colors: ReturnType<typeof useColors>;
  onOpenDiff: (doc: DocumentListItem) => void;
  onOpenReview: (jobId: string) => void;
}) {
  const styles = makeStyles(colors);
  const hasDiff = doc.version_count >= 2 && !!doc.latest_version;
  const hasJob = !!doc.latest_job && doc.latest_job.state === 'done';
  const isAnalysing =
    !!doc.latest_job && ['queued', 'running'].includes(doc.latest_job.state);

  const date = doc.created_at
    ? new Date(doc.created_at).toLocaleDateString('id-ID', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : '';

  return (
    <View style={styles.docCard}>
      <View style={styles.docCardHeader}>
        <View style={styles.docCardIcon}>
          <Feather name="file-text" size={18} color={colors.primary} />
        </View>
        <View style={styles.docCardMeta}>
          <Text style={styles.docTitle} numberOfLines={2}>
            {doc.title}
          </Text>
          {doc.counterparty && (
            <Text style={styles.docCounterparty} numberOfLines={1}>
              {doc.counterparty}
            </Text>
          )}
          <Text style={styles.docDate}>
            {date} · v{doc.version_count}
          </Text>
        </View>
      </View>

      {/* State badges */}
      {isAnalysing && (
        <View style={[styles.badge, { backgroundColor: colors.amberBg, borderColor: colors.amberBorder }]}>
          <ActivityIndicator size="small" color={colors.amber} style={{ marginRight: 4 }} />
          <Text style={[styles.badgeText, { color: colors.amberForeground }]}>Analisis berjalan…</Text>
        </View>
      )}

      {/* Action row */}
      <View style={styles.docActions}>
        {hasDiff && (
          <Pressable
            style={({ pressed }) => [styles.actionBtn, pressed && { opacity: 0.7 }]}
            onPress={() => onOpenDiff(doc)}
          >
            <Feather name="git-merge" size={14} color={colors.primary} />
            <Text style={styles.actionBtnText}>Lihat Diff</Text>
          </Pressable>
        )}
        {hasJob && doc.latest_job && (
          <Pressable
            style={({ pressed }) => [styles.actionBtn, styles.actionBtnPrimary, pressed && { opacity: 0.8 }]}
            onPress={() => onOpenReview(doc.latest_job!.job_id)}
          >
            <Feather name="eye" size={14} color={colors.primaryForeground} />
            <Text style={[styles.actionBtnText, { color: colors.primaryForeground }]}>Tinjau Analisis</Text>
          </Pressable>
        )}
        {!hasDiff && !hasJob && !isAnalysing && (
          <Text style={styles.noActionHint}>
            {doc.version_count < 2
              ? 'Upload versi baru via web untuk melihat diff'
              : 'Mulai analisis dari halaman diff'}
          </Text>
        )}
      </View>
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
    center: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 20,
      paddingBottom: 12,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
      backgroundColor: colors.card,
    },
    brandRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
    },
    brandIcon: {
      width: 28,
      height: 28,
      borderRadius: 8,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    brandName: {
      fontSize: 18,
      fontWeight: '700' as const,
      color: colors.primary,
      letterSpacing: 3,
      fontFamily: 'Inter_700Bold',
    },
    headerRight: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      maxWidth: 160,
    },
    userEmail: {
      fontSize: 12,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      flexShrink: 1,
    },
    iconBtn: {
      padding: 4,
    },
    disclaimerRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      backgroundColor: colors.muted,
      paddingHorizontal: 16,
      paddingVertical: 8,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    disclaimerText: {
      fontSize: 11,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      flex: 1,
      lineHeight: 15,
    },
    listContent: {
      padding: 16,
      paddingBottom: 24,
    },
    emptyContent: {
      flexGrow: 1,
    },
    sectionTitle: {
      fontSize: 13,
      fontWeight: '600' as const,
      color: colors.mutedForeground,
      fontFamily: 'Inter_600SemiBold',
      textTransform: 'uppercase' as const,
      letterSpacing: 0.8,
      marginBottom: 12,
    },
    separator: {
      height: 10,
    },
    emptyState: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: 60,
      gap: 10,
    },
    emptyTitle: {
      fontSize: 17,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
    },
    emptySub: {
      fontSize: 14,
      color: colors.mutedForeground,
      textAlign: 'center' as const,
      fontFamily: 'Inter_400Regular',
      lineHeight: 20,
      maxWidth: 260,
    },
    errorTitle: {
      fontSize: 17,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
      marginTop: 12,
    },
    errorSub: {
      fontSize: 14,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      textAlign: 'center' as const,
      marginTop: 4,
    },
    retryBtn: {
      marginTop: 16,
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
    docCard: {
      backgroundColor: colors.card,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: colors.border,
      padding: 16,
      gap: 12,
    },
    docCardHeader: {
      flexDirection: 'row',
      gap: 12,
    },
    docCardIcon: {
      width: 40,
      height: 40,
      borderRadius: 10,
      backgroundColor: colors.muted,
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0,
    },
    docCardMeta: {
      flex: 1,
      gap: 2,
    },
    docTitle: {
      fontSize: 15,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
      lineHeight: 20,
    },
    docCounterparty: {
      fontSize: 13,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
    },
    docDate: {
      fontSize: 12,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      marginTop: 2,
    },
    badge: {
      flexDirection: 'row',
      alignItems: 'center',
      borderWidth: 1,
      borderRadius: 6,
      paddingHorizontal: 10,
      paddingVertical: 6,
      alignSelf: 'flex-start' as const,
    },
    badgeText: {
      fontSize: 12,
      fontFamily: 'Inter_500Medium',
      fontWeight: '500' as const,
    },
    docActions: {
      flexDirection: 'row',
      gap: 8,
      flexWrap: 'wrap' as const,
    },
    actionBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: 8,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.background,
    },
    actionBtnPrimary: {
      backgroundColor: colors.primary,
      borderColor: colors.primary,
    },
    actionBtnText: {
      fontSize: 13,
      fontWeight: '500' as const,
      color: colors.foreground,
      fontFamily: 'Inter_500Medium',
    },
    noActionHint: {
      fontSize: 12,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      fontStyle: 'italic' as const,
    },
  });
}
