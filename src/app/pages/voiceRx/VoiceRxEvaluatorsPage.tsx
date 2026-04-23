import { FileText } from 'lucide-react';
import { AppEvaluatorsPage } from '@/features/evals';

export function VoiceRxEvaluatorsPage() {
  return <AppEvaluatorsPage surface={{ icon: FileText, title: 'Evaluators' }} />;
}
