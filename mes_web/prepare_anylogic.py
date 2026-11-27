"""Build a local, isolated AnyLogic export from the workshop's reference model."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


INSTALLATION = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'AnyLogic 8.9 Professional'
EXPORT_NAME = 'Excel_Test_Konveyor_Simulation'
WORKBOOK = 'AnyLogic_Test_Plani.xlsx'


def isolate_paths(model):
    paths = {
        WORKBOOK: 'new java.io.File(System.getProperty("mes.anylogic.modelDir"), "AnyLogic_Test_Plani.xlsx").getPath()',
        'senaryo.txt': 'new java.io.File(System.getProperty("mes.anylogic.runDir"), "senaryo.txt").getPath()',
        'uretim_modu.txt': 'new java.io.File(System.getProperty("mes.anylogic.runDir"), "uretim_modu.txt").getPath()',
        'model': 'System.getProperty("mes.anylogic.runDir")',
    }
    for name, expression in paths.items():
        pattern = rf'<Code><!\[CDATA\["[A-Za-z]:/[^"\r\n]*/{re.escape(name)}"\]\]></Code>'
        model, count = re.subn(pattern, lambda _: f'<Code><![CDATA[{expression}]]></Code>', model)
        if count != 1:
            raise ValueError(f'Model yolu doğrulanamadı: {name}')
    if re.search(r'["\x27][A-Za-z]:[/\\]', model):
        raise ValueError('Modelde doğrulanmamış sabit dosya yolu var.')
    return model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path, help='Read-only reference Excel_Test_Konveyor.alp')
    parser.add_argument('--installation', type=Path, default=INSTALLATION)
    args = parser.parse_args()
    source = args.model.resolve(strict=True)
    project = Path(__file__).resolve().parent.parent
    local = (project / '.local').resolve()
    if not local.is_relative_to(project):
        raise ValueError('Yerel model klasörü proje kökünün içinde olmalı.')
    output = local / 'anylogic'
    if output.exists():
        raise FileExistsError(f'Yerel çıktı klasörü kullanımda: {output}')
    install = args.installation.resolve(strict=True)
    java = install / 'jre' / 'bin' / 'java.exe'
    javac = java.with_name('javac.exe')
    cli = install / 'AnyLogic.exe'
    for path in (java, javac, cli, source.with_name(WORKBOOK)):
        if not path.is_file():
            raise FileNotFoundError(path)
    model = isolate_paths(source.read_text(encoding='utf-8-sig'))
    model_dir = output / 'model'
    model_dir.mkdir(parents=True)
    copy = model_dir / 'Excel_Test_Konveyor.alp'
    copy.write_text(model, encoding='utf-8', newline='\n')
    shutil.copyfile(source.with_name(WORKBOOK), model_dir / WORKBOOK)
    export = output / 'export'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    subprocess.run([str(cli), '-e', '-o', str(export), f'{copy}:Simulation'], cwd=output, check=True,
                   timeout=300, creationflags=flags)
    runtime = export / EXPORT_NAME
    if not (runtime / 'model.jar').is_file():
        raise FileNotFoundError(runtime / 'model.jar')
    classpath = os.pathsep.join(str(path) for path in (runtime / 'model.jar', runtime / 'lib' / '*'))
    subprocess.run([str(javac), '-encoding', 'UTF-8', '-cp', classpath, '-d', str(output),
                    str(Path(__file__).with_name('anylogic_assets') / 'MesEngineBridge.java')],
                   cwd=output, check=True, timeout=60, creationflags=flags)
    manifest = {'schema': 1, 'java': str(java), 'model_sha256': hashlib.sha256(copy.read_bytes()).hexdigest()}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'AnyLogic export ready: {output}')


if __name__ == '__main__':
    main()
