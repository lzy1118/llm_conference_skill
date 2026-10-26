package org.grobid.service.process;

import java.io.InputStream;

import com.google.inject.Inject;
import com.google.inject.Singleton;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.core.Response.Status;
import org.grobid.core.GrobidModels;

@Singleton
public class GrobidRestProcessTraining {

    @Inject
    public GrobidRestProcessTraining() {
    }

    private Response disabled() {
        return Response.status(Status.SERVICE_UNAVAILABLE)
            .entity("Training endpoints are disabled in this filtered runtime bundle.")
            .build();
    }

    public static boolean containsModel(String targetModel) {
        return false;
    }

    public Response getModel(String model, String architecture) {
        return disabled();
    }

    public Response trainModel(
        String model,
        String architecture,
        String type,
        double ratio,
        int n,
        boolean incremental
    ) {
        return disabled();
    }

    public Response resultTraining(String token) {
        return disabled();
    }

    public Response createTraining(
        final InputStream inputStream,
        final String filename,
        final GrobidModels.Flavor flavor
    ) {
        return disabled();
    }
}
