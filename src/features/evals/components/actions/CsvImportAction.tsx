import { useState } from 'react';
import { Upload } from 'lucide-react';

import { Button } from '@/components/ui';
import { EvaluatorCSVImport } from '@/features/insideSales/components/EvaluatorCSVImport';

export function CsvImportAction() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Upload className="h-4 w-4" />
        Import CSV
      </Button>
      <EvaluatorCSVImport isOpen={open} onClose={() => setOpen(false)} />
    </>
  );
}
