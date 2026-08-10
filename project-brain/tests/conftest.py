from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from brain.database import Database
from core.config import BrainConfig
from core.paths import BrainPaths

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

PHP_CONTROLLER_SAMPLE = """<?php
namespace App\\Controllers;

use App\\Models\\PedidoModel;

class PedidoController extends BaseController
{
    protected $pedidoModel;

    public function imprimirLote()
    {
        $inicio = $this->request->getGet('inicio');
        $fim = $this->request->getGet('fim');
        // TODO: limitar intervalo de pedidos para no maximo 50
        $pedidos = new PedidoModel();
        return $pedidos->findAll();
    }

    public function index()
    {
        return view('pedido/index');
    }
}
"""

PHP_MODEL_SAMPLE = """<?php
namespace App\\Models;

use CodeIgniter\\Model;

class PedidoModel extends Model
{
    protected $table = 'tab_pedido';

    public function buscarPorId($id)
    {
        return $this->find($id);
    }
}
"""

PHP_MIGRATION_SAMPLE = """<?php
namespace App\\Database\\Migrations;

use CodeIgniter\\Database\\Migration;

class CreateTabPedido extends Migration
{
    public function up()
    {
        $this->forge->addField([
            'ped_id' => ['type' => 'INT', 'auto_increment' => true],
            'ped_numero' => ['type' => 'VARCHAR', 'constraint' => 20],
        ]);
        $this->forge->addKey('ped_id', true);
        $this->forge->createTable('tab_pedido');
    }

    public function down()
    {
        $this->forge->dropTable('tab_pedido');
    }
}
"""


@pytest.fixture
def brain_paths(tmp_path) -> BrainPaths:
    home = tmp_path / "brain_home"
    home.mkdir()
    return BrainPaths(
        home=home,
        db_path=home / "project_brain.db",
        config_path=home / "config.yaml",
        state_path=home / "state.json",
        task_data_dir=home / "task-data",
        migrations_dir=PACKAGE_ROOT / "migrations",
        templates_dir=PACKAGE_ROOT / "templates",
    )


@pytest.fixture
def db(brain_paths) -> Database:
    database = Database(brain_paths.db_path, brain_paths.migrations_dir)
    yield database
    database.close()


@pytest.fixture
def config() -> BrainConfig:
    return BrainConfig()


@pytest.fixture
def php_project(tmp_path) -> Path:
    root = tmp_path / "sample_php_project"
    (root / "app" / "Controllers").mkdir(parents=True)
    (root / "app" / "Models").mkdir(parents=True)
    (root / "app" / "Database" / "Migrations").mkdir(parents=True)
    (root / "app" / "Controllers" / "Pedido.php").write_text(PHP_CONTROLLER_SAMPLE, encoding="utf-8")
    (root / "app" / "Models" / "PedidoModel.php").write_text(PHP_MODEL_SAMPLE, encoding="utf-8")
    (root / "app" / "Database" / "Migrations" / "001_CreateTabPedido.php").write_text(
        PHP_MIGRATION_SAMPLE, encoding="utf-8"
    )
    return root
