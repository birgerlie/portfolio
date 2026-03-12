"""gRPC server startup and lifecycle."""

from concurrent import futures

import grpc

from fund.proto import fund_service_pb2_grpc


def create_server(servicer, port=50051, max_workers=10):
    """Create and configure a gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    fund_service_pb2_grpc.add_FundServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    return server


def run_server(servicer, port=50051):
    """Start the gRPC server and block until terminated."""
    server = create_server(servicer, port=port)
    server.start()
    print(f"Fund gRPC server started on port {port}")
    server.wait_for_termination()
    return server
