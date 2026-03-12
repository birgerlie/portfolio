"""Tests for gRPC server runner."""

from unittest.mock import MagicMock, patch

from fund.grpc_runner import create_server


class TestCreateServer:
    @patch("fund.grpc_runner.grpc.server")
    def test_creates_server_on_port(self, mock_grpc_server):
        mock_server = MagicMock()
        mock_grpc_server.return_value = mock_server

        servicer = MagicMock()
        server = create_server(servicer, port=50051)

        assert server == mock_server
        mock_server.add_insecure_port.assert_called_once_with("[::]:50051")
