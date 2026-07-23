/**
 * Tabs layout — LANDY Mobile uses a stack-based flow (login → docs → diff → review),
 * so this group is a simple pass-through Slot with no tab bar chrome.
 */
import { Slot } from 'expo-router';

export default function TabsLayout() {
  return <Slot />;
}
