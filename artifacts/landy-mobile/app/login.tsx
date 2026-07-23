import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { Feather } from '@expo/vector-icons';
import { useColors } from '@/hooks/useColors';
import { useAuth } from '@/context/auth';
import { login, verifyOTP } from '@/lib/api';

type Stage = 'email' | 'otp';

export default function LoginScreen() {
  const colors = useColors();
  const styles = makeStyles(colors);
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { setSession } = useAuth();

  const [stage, setStage] = useState<Stage>('email');
  const [email, setEmail] = useState('');
  const [challengeId, setChallengeId] = useState('');
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debugOtp, setDebugOtp] = useState<string | null>(null);

  async function handleRequestOtp() {
    if (!email.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const result = await login(email.trim().toLowerCase());
      setChallengeId(result.challenge_id);
      if (result.debug_otp) setDebugOtp(result.debug_otp);
      setStage('otp');
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Gagal mengirim OTP.');
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp() {
    if (!otp.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const result = await verifyOTP(challengeId, otp.trim());
      await setSession(result.token, {
        user_id: result.user_id,
        email: result.email,
        display_name: result.display_name,
      });
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Kode OTP tidak valid.');
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally {
      setLoading(false);
    }
  }

  const topPad = Platform.OS === 'web' ? 67 : insets.top;
  const bottomPad = Platform.OS === 'web' ? 34 : insets.bottom;

  return (
    <KeyboardAvoidingView
      style={[styles.root, { paddingTop: topPad, paddingBottom: bottomPad }]}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Brand mark */}
      <View style={styles.brand}>
        <View style={styles.brandIcon}>
          <Feather name="shield" size={20} color={colors.primaryForeground} />
        </View>
        <Text style={styles.brandName}>LANDY</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.heading}>
          {stage === 'email' ? 'Masuk ke akun Anda' : 'Masukkan kode OTP'}
        </Text>
        <Text style={styles.subheading}>
          {stage === 'email'
            ? 'Kami akan mengirim kode verifikasi ke email Anda.'
            : `Kode dikirim ke ${email}${debugOtp ? ` (dev: ${debugOtp})` : ''}`}
        </Text>

        {error && (
          <View style={styles.errorBox}>
            <Feather name="alert-circle" size={14} color={colors.destructive} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {stage === 'email' ? (
          <>
            <View style={styles.field}>
              <Text style={styles.label}>Email</Text>
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="nama@email.com"
                placeholderTextColor={colors.mutedForeground}
                returnKeyType="send"
                onSubmitEditing={handleRequestOtp}
                editable={!loading}
              />
            </View>
            <Pressable
              style={({ pressed }) => [styles.btn, pressed && styles.btnPressed, loading && styles.btnDisabled]}
              onPress={handleRequestOtp}
              disabled={loading || !email.trim()}
            >
              {loading ? (
                <ActivityIndicator size="small" color={colors.primaryForeground} />
              ) : (
                <Text style={styles.btnText}>Kirim Kode</Text>
              )}
            </Pressable>
          </>
        ) : (
          <>
            <View style={styles.field}>
              <Text style={styles.label}>Kode OTP</Text>
              <TextInput
                style={[styles.input, styles.otpInput]}
                value={otp}
                onChangeText={setOtp}
                keyboardType="number-pad"
                placeholder="• • • • • •"
                placeholderTextColor={colors.mutedForeground}
                maxLength={6}
                returnKeyType="done"
                onSubmitEditing={handleVerifyOtp}
                editable={!loading}
                autoFocus
              />
            </View>
            <Pressable
              style={({ pressed }) => [styles.btn, pressed && styles.btnPressed, loading && styles.btnDisabled]}
              onPress={handleVerifyOtp}
              disabled={loading || otp.trim().length < 4}
            >
              {loading ? (
                <ActivityIndicator size="small" color={colors.primaryForeground} />
              ) : (
                <Text style={styles.btnText}>Verifikasi</Text>
              )}
            </Pressable>
            <Pressable
              style={styles.backLink}
              onPress={() => { setStage('email'); setOtp(''); setError(null); }}
            >
              <Text style={styles.backLinkText}>Kembali</Text>
            </Pressable>
          </>
        )}
      </View>

      <Text style={styles.disclaimer}>
        LANDY adalah alat bantu AI — bukan pengganti nasihat hukum.
      </Text>
    </KeyboardAvoidingView>
  );
}

function makeStyles(colors: ReturnType<typeof useColors>) {
  return StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: colors.background,
      paddingHorizontal: 24,
      justifyContent: 'center',
    },
    brand: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      marginBottom: 32,
      justifyContent: 'center',
    },
    brandIcon: {
      width: 36,
      height: 36,
      borderRadius: 10,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    brandName: {
      fontSize: 24,
      fontWeight: '700' as const,
      color: colors.primary,
      letterSpacing: 3,
      fontFamily: 'Inter_700Bold',
    },
    card: {
      backgroundColor: colors.card,
      borderRadius: 16,
      padding: 24,
      borderWidth: 1,
      borderColor: colors.border,
    },
    heading: {
      fontSize: 20,
      fontWeight: '700' as const,
      color: colors.foreground,
      fontFamily: 'Inter_700Bold',
      marginBottom: 6,
    },
    subheading: {
      fontSize: 14,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
      lineHeight: 20,
      marginBottom: 20,
    },
    errorBox: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 8,
      backgroundColor: colors.redBg,
      borderRadius: 8,
      borderWidth: 1,
      borderColor: colors.redBorder,
      padding: 12,
      marginBottom: 16,
    },
    errorText: {
      fontSize: 13,
      color: colors.destructive,
      fontFamily: 'Inter_400Regular',
      flex: 1,
    },
    field: {
      marginBottom: 16,
    },
    label: {
      fontSize: 13,
      fontWeight: '600' as const,
      color: colors.foreground,
      fontFamily: 'Inter_600SemiBold',
      marginBottom: 6,
    },
    input: {
      borderWidth: 1,
      borderColor: colors.input,
      borderRadius: 8,
      padding: 12,
      fontSize: 15,
      color: colors.foreground,
      backgroundColor: colors.background,
      fontFamily: 'Inter_400Regular',
    },
    otpInput: {
      fontSize: 22,
      letterSpacing: 8,
      textAlign: 'center' as const,
      fontFamily: 'Inter_600SemiBold',
    },
    btn: {
      backgroundColor: colors.primary,
      borderRadius: 10,
      paddingVertical: 14,
      alignItems: 'center',
    },
    btnPressed: {
      opacity: 0.8,
    },
    btnDisabled: {
      opacity: 0.5,
    },
    btnText: {
      color: colors.primaryForeground,
      fontSize: 15,
      fontWeight: '600' as const,
      fontFamily: 'Inter_600SemiBold',
    },
    backLink: {
      alignItems: 'center',
      marginTop: 14,
    },
    backLinkText: {
      fontSize: 14,
      color: colors.mutedForeground,
      fontFamily: 'Inter_400Regular',
    },
    disclaimer: {
      fontSize: 12,
      color: colors.mutedForeground,
      textAlign: 'center',
      marginTop: 28,
      fontFamily: 'Inter_400Regular',
      lineHeight: 16,
    },
  });
}
