/**
 * LANDY Mobile design tokens — derived from the sibling web artifact (index.css).
 * Primary: dark navy (light) / bright blue-violet (dark)
 * Accent colours: amber (warnings), rose (material changes), violet (analysis prompt)
 */
const colors = {
  light: {
    text: '#1B2140',
    tint: '#122070',

    background: '#FAF9F6',
    foreground: '#1B2140',

    card: '#FFFFFF',
    cardForeground: '#1B2140',

    primary: '#122070',
    primaryForeground: '#FAF9F6',

    secondary: '#E5E9F0',
    secondaryForeground: '#1B2140',

    muted: '#EDEBE6',
    mutedForeground: '#697490',

    accent: '#E5E9F0',
    accentForeground: '#1B2140',

    destructive: '#F04040',
    destructiveForeground: '#FAFAFA',

    border: '#D0D5E1',
    input: '#D0D5E1',

    // Semantic alert colours
    amber: '#D97706',
    amberBg: '#FFFBEB',
    amberBorder: '#FCD34D',
    amberForeground: '#92400E',

    rose: '#E11D48',
    roseBg: '#FFF1F2',
    roseBorder: '#FECDD3',
    roseForeground: '#9F1239',

    violet: '#7C3AED',
    violetBg: '#F5F3FF',
    violetBorder: '#DDD6FE',
    violetForeground: '#4C1D95',

    green: '#16A34A',
    greenBg: '#F0FDF4',
    greenBorder: '#BBF7D0',

    red: '#DC2626',
    redBg: '#FEF2F2',
    redBorder: '#FECACA',
  },

  dark: {
    text: '#F5F3EE',
    tint: '#5070E0',

    background: '#0F1320',
    foreground: '#F5F3EE',

    card: '#131A2E',
    cardForeground: '#F5F3EE',

    primary: '#5070E0',
    primaryForeground: '#0F1320',

    secondary: '#1E2940',
    secondaryForeground: '#F5F3EE',

    muted: '#1A2235',
    mutedForeground: '#93A3BE',

    accent: '#1E2940',
    accentForeground: '#F5F3EE',

    destructive: '#7A1515',
    destructiveForeground: '#FAFAFA',

    border: '#273048',
    input: '#273048',

    amber: '#F59E0B',
    amberBg: '#1C1500',
    amberBorder: '#92400E',
    amberForeground: '#FCD34D',

    rose: '#FB7185',
    roseBg: '#1A0A0E',
    roseBorder: '#9F1239',
    roseForeground: '#FECDD3',

    violet: '#A78BFA',
    violetBg: '#1A1030',
    violetBorder: '#4C1D95',
    violetForeground: '#DDD6FE',

    green: '#4ADE80',
    greenBg: '#052E16',
    greenBorder: '#166534',

    red: '#F87171',
    redBg: '#1A0505',
    redBorder: '#991B1B',
  },

  radius: 8,
};

export default colors;
