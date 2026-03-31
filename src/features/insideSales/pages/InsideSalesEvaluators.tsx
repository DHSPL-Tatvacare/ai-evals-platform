import { useState } from 'react';
import { Upload } from 'lucide-react';
import { PermissionGate } from '@/components/auth/PermissionGate';
import { Button } from '@/components/ui';
import { AppEvaluatorsPage } from '@/features/evals';
import { routes } from '@/config/routes';
import { useNavigate } from 'react-router-dom';
import { EvaluatorCSVImport } from '../components/EvaluatorCSVImport';

export function InsideSalesEvaluators() {
  const navigate = useNavigate();
  const [showCSVImport, setShowCSVImport] = useState(false);

  const renderImportButton = () => (
    <PermissionGate action="resource:create">
      <Button
        variant="secondary"
        onClick={() => setShowCSVImport(true)}
      >
        <Upload className="h-4 w-4" />
        Import CSV
      </Button>
    </PermissionGate>
  );

  return (
    <>
      <AppEvaluatorsPage
        extraHeaderActions={renderImportButton()}
        extraEmptyStateActions={renderImportButton()}
        onOpenEvaluator={(evaluator) => navigate(routes.insideSales.evaluatorDetail(evaluator.id))}
      />

      <EvaluatorCSVImport
        isOpen={showCSVImport}
        onClose={() => setShowCSVImport(false)}
      />
    </>
  );
}
